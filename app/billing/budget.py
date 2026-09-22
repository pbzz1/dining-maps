"""이용권과 AI 예산. "요금제를 최대로 써도 LLM 비용이 선불 금액을 넘지 않는다"를 지키는 곳.

호출 흐름 (app/recommend/personal.py claude_json):
    est = estimate_input_tokens(...)            -- 입력 토큰 상한 추정
    r = reserve(user_id, kind, est, plan)        -- 최악 비용을 이용권에서 먼저 예약. 모자라면 Denied
    ... Anthropic 호출 ...
    settle(r, usage, outcome)                    -- 실제 비용을 spent 에 더하고 예약을 푼다

예약은 UPDATE 한 문장의 WHERE 로 검사하므로 동시 요청이 와도 예산을 넘을 수 없다. 정산이 안 되고
서버가 죽으면 예약이 남아 예산이 줄어들 뿐, 넘치지는 않는다(손해 없음 쪽으로만 틀린다).

캐시 적중(llm_reco_cache)은 여기 오지 않는다 -- 비용이 0이라 예약할 게 없다.
"""
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import ROUND_UP, Decimal

from app.billing.plans import (
    CACHE_READ_MULT, CACHE_WRITE_MULT, FREE, INPUT_TOKEN_CAP, PERIOD_DAYS, PLANS, USD_KRW, Plan, get_plan,
)
from app.db import connect

KST = timezone(timedelta(hours=9))
KRW = Decimal("0.001")


class Denied(Exception):
    """LLM 을 부르지 않기로 한 이유. 호출부는 무료 방식으로 답한다.
    reason: no_plan(이용권 없음·만료·취소) / budget(예산 소진) / daily(하루 상한) / input(입력이 너무 김)"""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Reservation:
    spend_id: int
    entitlement_id: int
    plan: Plan
    est_input_tokens: int
    worst_krw: Decimal


# ---------------------------------------------------------------- 비용 산수

def estimate_input_tokens(system: str, messages: list[dict], schema: dict | None = None) -> int:
    """실제 입력 토큰 수 이상이 되도록 세는 상한 추정. 정확한 수가 아니라 "넘지 않는 수"가 목적이다.

    토크나이저를 여기서 돌릴 수 없어(패키지 없음, Lambda 크기) 문자 단위로 보수적으로 센다:
    한글 등 비ASCII 문자는 글자당 2토큰, 숫자·기호는 1토큰, 영문자는 3자당 1토큰, 줄바꿈 1토큰.
    구조화 출력 스키마(enum 에 후보 메뉴명이 들어간다)도 입력으로 친다. 메시지마다 프레임 오버헤드를 더한다.
    실제 usage.input_tokens 와의 차이는 llm_spend 에 남아 감시한다(입력 추정 ≥ 실제여야 한다).
    """
    def count(text: str) -> int:
        letters = 0
        tokens = 0
        for ch in text:
            if ord(ch) > 127:
                tokens += 2
            elif ch.isalpha():
                letters += 1
            elif ch.isdigit() or (not ch.isspace()):
                tokens += 1
            elif ch == "\n":
                tokens += 1
        return tokens + (letters + 2) // 3

    total = count(system) + 16
    for m in messages:
        content = m["content"] if isinstance(m["content"], str) else json.dumps(m["content"], ensure_ascii=False)
        total += count(content) + 8
    if schema:
        # 구조화 출력은 스키마 본문보다 훨씬 많은 토큰을 더한다 -- 실측(2026-09-22, count_tokens 와 실제 usage 비교):
        # 스키마 JSON 이 약 600토큰일 때 실제 입력 증가분은 590~880토큰(문법 프롬프트가 붙는다). 1.5배 + 300 으로 덮는다.
        total += int(count(json.dumps(schema, ensure_ascii=False)) * 1.5) + 300
    return total + 200


def _usd_to_krw(usd: Decimal) -> Decimal:
    # 올림 -- 비용은 크게 잡는 쪽이 안전하다.
    return (usd * USD_KRW).quantize(KRW, rounding=ROUND_UP)


def worst_cost_krw(plan: Plan, est_input_tokens: int) -> Decimal:
    """이 호출이 최대로 들 수 있는 원화 비용. 출력은 max_tokens 를 넘을 수 없다."""
    usd = (Decimal(est_input_tokens) * plan.input_usd_per_mtok + Decimal(plan.max_tokens) * plan.output_usd_per_mtok) / 1_000_000
    return _usd_to_krw(usd)


def actual_cost_krw(plan: Plan, usage) -> Decimal:
    """응답 usage 로 계산한 실제 비용. usage 는 SDK 객체나 dict 둘 다 받는다."""
    get = (lambda k: getattr(usage, k, None)) if not isinstance(usage, dict) else usage.get
    inp = Decimal(get("input_tokens") or 0)
    out = Decimal(get("output_tokens") or 0)
    cw = Decimal(get("cache_creation_input_tokens") or 0)
    cr = Decimal(get("cache_read_input_tokens") or 0)
    usd = ((inp + cw * CACHE_WRITE_MULT + cr * CACHE_READ_MULT) * plan.input_usd_per_mtok + out * plan.output_usd_per_mtok) / 1_000_000
    return _usd_to_krw(usd)


# ---------------------------------------------------------------- 이용권 조회

def active_entitlement(conn, user_id) -> dict | None:
    """지금 유효한 이용권 한 행. 없으면 None(= 무료). 겹치면 먼저 시작한 것."""
    return conn.execute(
        """SELECT * FROM entitlement
           WHERE user_id = %s AND revoked_at IS NULL AND starts_at <= now() AND now() < ends_at
           ORDER BY starts_at, id LIMIT 1""",
        (user_id,),
    ).fetchone()


def plan_of(entitlement: dict | None) -> Plan | None:
    return get_plan(entitlement["plan"]) if entitlement else None


def budget_left_pct(entitlement: dict | None) -> int | None:
    if not entitlement or not entitlement["budget_krw"]:
        return None
    left = entitlement["budget_krw"] - entitlement["spent_krw"] - entitlement["reserved_krw"]
    return max(0, min(100, int(left * 100 / entitlement["budget_krw"])))


def kst_day_start(now: datetime | None = None) -> datetime:
    d = (now or datetime.now(KST)).astimezone(KST).date()
    return datetime(d.year, d.month, d.day, tzinfo=KST)


def used_today(conn, user_id) -> int:
    return conn.execute(
        "SELECT count(*) AS n FROM llm_spend WHERE user_id = %s AND created_at >= %s",
        (user_id, kst_day_start()),
    ).fetchone()["n"]


def status(conn, user_id) -> dict:
    """/api/auth/me 와 /api/billing/me 가 같은 값을 돌려주도록 한 곳에서 만든다."""
    ent = active_entitlement(conn, user_id)
    plan = plan_of(ent)
    return {
        "plan": plan.key if plan else FREE,
        "plan_ends_at": ent["ends_at"] if ent else None,
        "ai_budget_left_pct": budget_left_pct(ent),
        "daily_limit": plan.daily_limit if plan else None,
        "used_today": used_today(conn, user_id) if plan else None,
    }


# ---------------------------------------------------------------- 발급·취소

def grant(conn, user_id, plan_key: str, order_id: str | None = None, days: int = PERIOD_DAYS) -> dict:
    """이용권 발급. 같은 요금제를 이어 사면 현재(또는 예정된) 만료일 다음부터 시작한다 -- 겹쳐서 날짜를
    잃지 않게. 결제 없이 운영자가 발급할 때는 order_id 없이 부른다(scripts/billing/grant_entitlement.py)."""
    plan = get_plan(plan_key)
    row = conn.execute(
        "SELECT max(ends_at) AS ends_at FROM entitlement WHERE user_id = %s AND revoked_at IS NULL", (user_id,)
    ).fetchone()
    now = datetime.now(timezone.utc)
    starts_at = max(now, row["ends_at"]) if row and row["ends_at"] else now
    return conn.execute(
        """INSERT INTO entitlement (user_id, plan, starts_at, ends_at, budget_krw, payment_order_id)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING *""",
        (user_id, plan.key, starts_at, starts_at + timedelta(days=days), plan.budget_krw, order_id),
    ).fetchone()


def revoke_by_order(conn, order_id: str) -> int:
    """환불·취소된 주문의 이용권을 즉시 무효화한다. 무효화된 행 수."""
    return conn.execute(
        "UPDATE entitlement SET revoked_at = now() WHERE payment_order_id = %s AND revoked_at IS NULL", (order_id,)
    ).rowcount


# ---------------------------------------------------------------- 예약·정산

def reserve(user_id, kind: str, est_input_tokens: int, entitlement_id: int | None = None) -> Reservation:
    """호출 전에 최악 비용을 예약한다. 안 되면 Denied. 한 트랜잭션:
    이용권 행 잠금(하루 상한을 정확히 세기 위해) -> 오늘 호출 수 -> 조건부 UPDATE(예산) -> 원장 행."""
    if est_input_tokens > INPUT_TOKEN_CAP:
        raise Denied("input")
    with connect() as conn:
        if entitlement_id is None:
            ent = active_entitlement(conn, user_id)
            entitlement_id = ent["id"] if ent else None
        ent = conn.execute(
            """SELECT * FROM entitlement WHERE id = %s AND user_id = %s AND revoked_at IS NULL
                 AND starts_at <= now() AND now() < ends_at FOR UPDATE""",
            (entitlement_id, user_id),
        ).fetchone() if entitlement_id is not None else None
        if ent is None:
            raise Denied("no_plan")
        plan = get_plan(ent["plan"])
        if used_today(conn, user_id) >= plan.daily_limit:
            raise Denied("daily")
        worst = worst_cost_krw(plan, est_input_tokens)
        # 예산 검사는 이 한 문장이 전부다 -- 잠금이 풀려 있어도 이 조건만으로 예산을 넘을 수 없다.
        row = conn.execute(
            """UPDATE entitlement SET reserved_krw = reserved_krw + %s
               WHERE id = %s AND revoked_at IS NULL AND now() < ends_at
                 AND spent_krw + reserved_krw + %s <= budget_krw
               RETURNING id""",
            (worst, ent["id"], worst),
        ).fetchone()
        if row is None:
            raise Denied("budget")
        spend = conn.execute(
            """INSERT INTO llm_spend (user_id, entitlement_id, kind, model, est_input_tokens, max_tokens, worst_krw)
               VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (user_id, ent["id"], kind, plan.model, est_input_tokens, plan.max_tokens, worst),
        ).fetchone()
    return Reservation(spend["id"], ent["id"], plan, est_input_tokens, worst)


def settle(r: Reservation, usage=None, outcome: str = "ok") -> Decimal:
    """실제 비용을 확정하고 예약을 푼다. 두 번 불러도 한 번만 반영된다(settled_at 으로 막는다).

    usage 가 없는데 outcome 이 unknown(타임아웃·연결 끊김: 처리됐을 수도 있다)이면 최악 비용을 실제로
    친다 -- 모르는 쪽은 손해 없는 방향으로. error(4xx/5xx 로 확실히 거절됨)면 0원.
    """
    if usage is not None:
        actual = actual_cost_krw(r.plan, usage)
        get = (lambda k: getattr(usage, k, None)) if not isinstance(usage, dict) else usage.get
        inp, out = get("input_tokens"), get("output_tokens")
        if inp is not None and inp > r.est_input_tokens:
            # 추정이 상한이 아니었다 -- 손해 없음의 전제가 깨진 것이니 눈에 띄게 남긴다.
            print(f"llm_spend {r.spend_id}: input_tokens {inp} > estimate {r.est_input_tokens}")
    else:
        actual = r.worst_krw if outcome == "unknown" else Decimal(0)
        inp = out = None
    with connect() as conn:
        done = conn.execute(
            """UPDATE llm_spend SET input_tokens = %s, output_tokens = %s, actual_krw = %s, outcome = %s,
                                    settled_at = now()
               WHERE id = %s AND settled_at IS NULL""",
            (inp, out, actual, outcome, r.spend_id),
        ).rowcount
        if done:
            conn.execute(
                "UPDATE entitlement SET reserved_krw = reserved_krw - %s, spent_krw = spent_krw + %s WHERE id = %s",
                (r.worst_krw, actual, r.entitlement_id),
            )
    return actual


def all_plans() -> list[Plan]:
    return list(PLANS.values())
