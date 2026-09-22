"""유료 요금제·이용권·AI 예산 검증. 로컬 DB에서만 돈다(운영 DB를 가리키면 거부).

    DATABASE_URL=postgresql://dining:dining@localhost:5432/dining_maps python scripts/eval/verify_billing.py

외부로 나가는 건 없다 -- Anthropic 은 httpx2.MockTransport, 토스는 app.billing.toss.transport 를 가짜로 바꾼다.
검사하는 것(하나라도 어기면 exit 1):
  1. 손해 없음: 최악 입력·출력으로 예산이 바닥날 때까지 부른다. 누적 실제 비용 ≤ 예산, 누적 최악 비용 ≤ 예산,
     spent + reserved ≤ 예산. 바닥나면 Denied(budget) 이고 그 뒤 LLM 호출은 0회.
  2. 동시 요청 20개가 같은 이용권을 예약해도 예약 합계가 예산을 넘지 않는다.
  3. 입력 추정: 최대 길이 한국어 대화(20턴 × 600자)도 잘라서 상한 안에 맞춘다. 추정치 ≥ 문자 기반 하한.
  4. 요금제별 요청 본문: Standard 는 claude-haiku-4-5 에 effort·thinking 없음, High 는 claude-sonnet-5 에 effort low.
  5. 권한: 결제 전·만료·환불 후·예산 소진에는 LLM 호출이 0회. 캐시 적중은 예산을 쓰지 않는다.
  6. 결제: 승인 성공 → 이용권, 같은 주문 중복 승인 → 이용권 1개, 금액 위조 → 400, 승인 실패 → 402,
     환불 웹훅 → 즉시 무효화, 이용 중 다른 요금제 → 409, 토스 키 없음 → 503.
  7. 타임아웃(결과 모름)은 최악 비용으로, 4xx 는 0원으로 정산된다. refusal 도 정산된다.
"""
import dataclasses
import json
import os
import sys
import threading
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-fake")  # claude_json 의 키 검사만 통과시킨다
os.environ.setdefault("JWT_SECRET", "verify-billing-secret")

import httpx2  # noqa: E402
from anthropic import DefaultHttpxClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.billing import budget, toss  # noqa: E402
from app.billing.plans import INPUT_TOKEN_CAP, PLANS, get_plan  # noqa: E402
from app.chat.schemas import ChatIn, ChatTurn  # noqa: E402
from app.chat.service import chat  # noqa: E402
from app.db import apply_schema, connect, get_connection, get_dsn  # noqa: E402
from app.main import app  # noqa: E402
from app.auth.deps import current_user  # noqa: E402
from app.recommend import personal  # noqa: E402

DSN = get_dsn()
if "localhost" not in DSN and "127.0.0.1" not in DSN:
    sys.exit(f"운영 DB 로 보이는 DATABASE_URL 에서는 돌지 않습니다: {DSN.split('@')[-1]}")

failures = []


def check(cond, msg):
    print(("  ok  " if cond else "  FAIL") + " " + msg)
    if not cond:
        failures.append(msg)


# ------------------------------------------------------------------ 가짜 Anthropic

class FakeAnthropic:
    """요청 본문을 기록하고 정해진 usage 로 답한다. mode: ok / worst / refusal / timeout / bad_request"""

    def __init__(self):
        self.requests = []
        self.mode = "ok"

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        if self.mode == "timeout":
            raise httpx2.ReadTimeout("slow", request=request)
        if self.mode == "bad_request":
            return httpx2.Response(400, json={"type": "error", "error": {"type": "invalid_request_error", "message": "bad"}})
        schema = body["output_config"]["format"]["schema"]
        menu_schema = schema["properties"]["picks"]["items"]["properties"]["menu"]
        labels = menu_schema.get("enum") or []
        if "reply" in schema["properties"]:
            payload = {"reply": "가볍게 골라봤어요.", "picks": [{"menu": labels[0], "reason": "가벼워요"}] if labels else [],
                       "new_memories": []}
        else:
            payload = {"picks": [{"menu": l, "reason": "테스트"} for l in labels[:3]], "comment": "테스트 조언", "new_memories": []}
        if self.mode == "worst":
            # 입력 추정치와 똑같은 입력 토큰 + max_tokens 출력 = 이 호출의 최악 비용 그대로
            est = budget.estimate_input_tokens(body["system"], body["messages"], schema)
            usage = {"input_tokens": est, "output_tokens": body["max_tokens"]}
        else:
            usage = {"input_tokens": 2500, "output_tokens": 300}
        stop = "refusal" if self.mode == "refusal" else "end_turn"
        return httpx2.Response(200, json={
            "id": "msg_test", "type": "message", "role": "assistant", "model": body["model"],
            "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
            "stop_reason": stop, "stop_sequence": None, "usage": usage,
        })


fake = FakeAnthropic()
personal.http_client = DefaultHttpxClient(transport=httpx2.MockTransport(fake.handler))


# ------------------------------------------------------------------ 가짜 토스

class FakeToss:
    def __init__(self):
        self.calls = []
        self.fail_code = None       # 승인 실패를 흉내
        self.status = "DONE"        # 조회 응답 상태

    def transport(self, method, url, headers, body):
        self.calls.append((method, url, json.loads(body) if body else None))
        assert headers["Authorization"].startswith("Basic ")
        if url.endswith("/payments/confirm"):
            req = json.loads(body)
            if self.fail_code:
                return 400, {"code": self.fail_code, "message": "카드가 거절되었습니다."}
            return 200, {"paymentKey": req["paymentKey"], "orderId": req["orderId"], "totalAmount": req["amount"],
                         "status": "DONE", "method": "카드"}
        key = url.rsplit("/", 1)[-1]
        return 200, {"paymentKey": key, "orderId": self.order_for(key), "status": self.status, "totalAmount": 3900}

    def order_for(self, key):
        return key.replace("pk_", "", 1)


ftoss = FakeToss()
toss.transport = ftoss.transport


# ------------------------------------------------------------------ 준비

with connect() as conn:
    apply_schema(conn)
    uid = conn.execute(
        "INSERT INTO app_user (provider, provider_uid, nickname) VALUES ('test', %s, '검증') RETURNING id",
        (f"verify-billing-{os.getpid()}",),
    ).fetchone()["id"]
    conn.execute(
        "INSERT INTO user_profile (user_id, goal, max_calorie, exclude_drinks) VALUES (%s, 'diet', 700, true)", (uid,)
    )
print(f"test user {uid} on {DSN.split('@')[-1]}")

client = TestClient(app)
app.dependency_overrides[current_user] = lambda: {"id": uid, "provider": "test", "nickname": "검증", "created_at": "2026-01-01T00:00:00Z"}


def ent_row():
    c = get_connection()
    try:
        return budget.active_entitlement(c, uid)
    finally:
        c.close()


def revoke_all():
    with connect() as c:
        c.execute("UPDATE entitlement SET revoked_at = now() WHERE user_id = %s AND revoked_at IS NULL", (uid,))
        c.execute("DELETE FROM llm_reco_cache WHERE user_id = %s", (uid,))


def spend_rows():
    c = get_connection()
    try:
        return c.execute("SELECT * FROM llm_spend WHERE user_id = %s ORDER BY id", (uid,)).fetchall()
    finally:
        c.close()


def reset_spend():
    """원장을 비운다 -- 앞 절에서 쌓인 오늘 호출 수가 다음 절의 하루 상한에 걸리지 않게."""
    with connect() as c:
        c.execute("DELETE FROM llm_spend WHERE user_id = %s", (uid,))


def chat_body(msg="어제 과식해서 오늘은 가볍게", history=()):
    return ChatIn(message=msg, history=[ChatTurn(role=r, text=t) for r, t in history])


try:
    # -------------------------------------------------------------- 0. 요금제 산수
    print("\n[0] 요금제 산수")
    std, high = get_plan("standard"), get_plan("high")
    check(Decimal("1700") < std.budget_krw < Decimal("1702"), f"Standard 예산 {std.budget_krw}원 (순매출 50%)")
    check(Decimal("4319") < high.budget_krw < Decimal("4321"), f"High 예산 {high.budget_krw}원")
    w_std, w_high = budget.worst_cost_krw(std, INPUT_TOKEN_CAP), budget.worst_cost_krw(high, INPUT_TOKEN_CAP)
    check(w_std == Decimal("22.400"), f"Standard 호출당 최악 {w_std}원")
    check(w_high == Decimal("57.600"), f"High 호출당 최악 {w_high}원")
    check(budget.actual_cost_krw(std, {"input_tokens": INPUT_TOKEN_CAP, "output_tokens": std.max_tokens}) == w_std,
          "최악 usage 의 실제 비용 = 최악 비용")

    # -------------------------------------------------------------- 4. 요금제별 요청 본문
    print("\n[4] 요금제별 요청 본문")
    for key, model, effort in (("standard", "claude-haiku-4-5", None), ("high", "claude-sonnet-5", "low")):
        revoke_all()
        with connect() as c:
            budget.grant(c, uid, key)
        fake.requests.clear()
        res = personal.personal_reco(uid)
        check(res.source == "llm" and res.plan == key, f"{key}: 개인 추천 source=llm plan={res.plan}")
        body = fake.requests[-1]
        check(body["model"] == model, f"{key}: model={body['model']}")
        check(body["max_tokens"] == get_plan(key).max_tokens, f"{key}: max_tokens={body['max_tokens']}")
        check("thinking" not in body, f"{key}: thinking 없음")
        check(body["output_config"].get("effort") == effort, f"{key}: effort={body['output_config'].get('effort')}")
        check(body["output_config"]["format"]["type"] == "json_schema", f"{key}: 구조화 출력")
        out = chat({"id": uid}, chat_body())
        check(out.source == "llm" and fake.requests[-1]["model"] == model, f"{key}: 대화도 {model}")
        check(out.ai_budget_left_pct is not None and out.ai_budget_left_pct < 100, f"{key}: 남은 예산 {out.ai_budget_left_pct}%")
        rows = spend_rows()
        check(all(r["actual_krw"] is not None and r["actual_krw"] <= r["worst_krw"] for r in rows[-2:]),
              f"{key}: 원장 정산됨 actual≤worst ({rows[-1]['actual_krw']} ≤ {rows[-1]['worst_krw']})")
        check(rows[-1]["input_tokens"] <= rows[-1]["est_input_tokens"],
              f"{key}: 입력 추정 {rows[-1]['est_input_tokens']} ≥ 가짜 실제 {rows[-1]['input_tokens']}")

    # 캐시 적중은 예산을 쓰지 않는다
    n = len(fake.requests)
    before = ent_row()
    res2 = personal.personal_reco(uid)
    after = ent_row()
    check(res2.source == "llm" and len(fake.requests) == n, "같은 입력의 두 번째 개인 추천은 캐시 -- LLM 호출 없음")
    check(after["spent_krw"] == before["spent_krw"], "캐시 적중은 예산을 쓰지 않는다")

    # -------------------------------------------------------------- 7. 정산 규칙
    print("\n[7] 정산 규칙")
    fake.mode = "timeout"
    before = ent_row()
    r = chat({"id": uid}, chat_body("타임아웃 테스트"))
    row = spend_rows()[-1]
    check(r.source == "filter" and row["outcome"] == "unknown" and row["actual_krw"] == row["worst_krw"],
          f"타임아웃은 최악 비용으로 정산 ({row['actual_krw']}원), 답은 무료 방식")
    fake.mode = "bad_request"
    r = chat({"id": uid}, chat_body("400 테스트"))
    row = spend_rows()[-1]
    check(row["outcome"] == "error" and row["actual_krw"] == 0, "4xx 는 0원으로 정산")
    fake.mode = "refusal"
    r = chat({"id": uid}, chat_body("거절 테스트"))
    row = spend_rows()[-1]
    check(r.source == "filter" and row["outcome"] == "refusal" and row["actual_krw"] > 0, "refusal 도 usage 로 정산, 답은 무료 방식")
    after = ent_row()
    check(after["reserved_krw"] == 0, "정산 뒤 예약 잔액 0")
    fake.mode = "ok"

    # -------------------------------------------------------------- 3. 입력 추정·대화 자르기
    print("\n[3] 입력 추정과 대화 자르기")
    long_ko = "오늘은 점심으로 매운 걸 피하고 단백질이 많은 걸 먹고 싶은데 회사 근처에 있는 브랜드면 좋겠어요 " * 12
    long_ko = long_ko[:600]
    hist = [("user" if i % 2 == 0 else "assistant", long_ko) for i in range(20)]
    fake.requests.clear()
    out = chat({"id": uid}, chat_body("그래서 뭐 먹지", hist))
    body = fake.requests[-1]
    est = budget.estimate_input_tokens(body["system"], body["messages"], body["output_config"]["format"]["schema"])
    check(out.source == "llm" and est <= INPUT_TOKEN_CAP, f"최대 길이 대화도 잘라서 상한 안 ({est} ≤ {INPUT_TOKEN_CAP}, 메시지 {len(body['messages'])}개)")
    check(body["messages"][0]["role"] == "user", "잘린 뒤에도 user 로 시작")
    chars = sum(len(m["content"]) for m in body["messages"]) + len(body["system"])
    check(est >= chars, f"추정 {est} ≥ 문자 수 {chars} (한글 글자당 2토큰으로 세므로)")
    check(budget.estimate_input_tokens("", [{"role": "user", "content": "x" * 30000}], None) > INPUT_TOKEN_CAP,
          "터무니없이 긴 입력은 상한을 넘는다고 판정")

    # -------------------------------------------------------------- 5. 권한
    print("\n[5] 권한: 결제 전·만료·환불 후·예산 소진")
    def llm_calls_for_free_paths(label):
        n = len(fake.requests)
        with connect() as c:
            c.execute("DELETE FROM llm_reco_cache WHERE user_id = %s", (uid,))
        res = personal.personal_reco(uid)
        out = chat({"id": uid}, chat_body("아무거나 골라줘"))
        check(len(fake.requests) == n, f"{label}: LLM 호출 0회 (reco={res.source}, chat={out.source})")
        return res, out

    revoke_all()
    res, out = llm_calls_for_free_paths("이용권 없음")
    check(res.plan == "free" and out.plan == "free" and out.ai_budget_left_pct is None, "이용권 없음: plan=free")

    with connect() as c:
        budget.grant(c, uid, "standard")
        c.execute("UPDATE entitlement SET starts_at = now() - interval '40 days', ends_at = now() - interval '10 days' WHERE user_id = %s AND revoked_at IS NULL", (uid,))
    llm_calls_for_free_paths("만료된 이용권")

    with connect() as c:
        budget.grant(c, uid, "standard")
        c.execute("UPDATE entitlement SET revoked_at = now() WHERE user_id = %s AND revoked_at IS NULL", (uid,))
    llm_calls_for_free_paths("취소된 이용권")

    with connect() as c:
        budget.grant(c, uid, "standard")
        c.execute("UPDATE entitlement SET spent_krw = budget_krw WHERE user_id = %s AND revoked_at IS NULL", (uid,))
    res, out = llm_calls_for_free_paths("예산 소진")
    check(res.limit_reason == "budget" and out.limit_reason == "budget" and out.limit_reached, "예산 소진: limit_reason=budget")
    check("이번 기간 AI 사용량을 다 써서" in out.reply, f"예산 소진 안내: {out.reply[:40]}")
    check(res.ai_budget_left_pct == 0 and out.ai_budget_left_pct == 0, "예산 소진: 남은 양 0%")

    with connect() as c:
        c.execute("UPDATE entitlement SET spent_krw = 0 WHERE user_id = %s AND revoked_at IS NULL", (uid,))
        for _ in range(get_plan("standard").daily_limit):
            c.execute("INSERT INTO llm_spend (user_id, kind, model, est_input_tokens, max_tokens, worst_krw) VALUES (%s, 'chat', 'x', 1, 1, 0)", (uid,))
    res, out = llm_calls_for_free_paths("하루 상한")
    check(out.limit_reason == "daily" and "오늘 AI 대화 15회" in out.reply, f"하루 상한 안내: {out.reply[:30]}")
    with connect() as c:
        c.execute("DELETE FROM llm_spend WHERE user_id = %s AND model = 'x'", (uid,))

    # -------------------------------------------------------------- 1. 손해 없음
    print("\n[1] 손해 없음: 예산이 바닥날 때까지 최악 입력·출력으로 호출")
    revoke_all()
    big = dataclasses.replace(PLANS["standard"], daily_limit=10**6)  # 하루 상한을 치우고 예산만 본다
    PLANS["standard"] = big
    with connect() as c:
        ent = budget.grant(c, uid, "standard")
    fake.mode = "worst"
    system, schema = "너는 식사 코치다.", {"type": "object", "properties": {"picks": {"type": "array", "items": {"type": "object", "properties": {"menu": {"type": "string", "enum": ["a"]}}}}, "comment": {"type": "string"}}}
    msgs = [{"role": "user", "content": "가" * 3500}]  # 추정이 상한 근처(≈7.3k)가 되게
    est = budget.estimate_input_tokens(system, msgs, schema)
    check(est <= INPUT_TOKEN_CAP, f"샘플 입력 추정 {est} 토큰")
    calls, denied = 0, None
    for _ in range(10_000):
        try:
            personal.claude_json(system, msgs, schema, "reco", big, uid, ent["id"])
            calls += 1
        except budget.Denied as e:
            denied = e.reason
            break
    rows = [r for r in spend_rows() if r["entitlement_id"] == ent["id"]]
    total_actual = sum(r["actual_krw"] for r in rows)
    total_worst = sum(r["worst_krw"] for r in rows)
    e = ent_row()
    check(denied == "budget", f"{calls}회 뒤 Denied({denied})")
    check(total_actual <= ent["budget_krw"], f"누적 실제 비용 {total_actual} ≤ 예산 {ent['budget_krw']}")
    check(total_worst <= ent["budget_krw"], f"누적 최악 비용 {total_worst} ≤ 예산")
    check(e["spent_krw"] + e["reserved_krw"] <= e["budget_krw"], f"spent {e['spent_krw']} + reserved {e['reserved_krw']} ≤ budget")
    check(e["budget_krw"] - e["spent_krw"] < w_std, "남은 예산이 한 번 최악 비용보다 작다(예산을 거의 다 썼다)")
    n = len(fake.requests)
    try:
        personal.claude_json(system, msgs, schema, "reco", big, uid, ent["id"])
    except budget.Denied:
        pass
    check(len(fake.requests) == n, "바닥난 뒤 LLM 호출 0회")
    fake.mode = "ok"

    # -------------------------------------------------------------- 2. 동시 요청
    print("\n[2] 동시 요청 20개")
    revoke_all()
    reset_spend()
    with connect() as c:
        ent = budget.grant(c, uid, "high")
        c.execute("UPDATE entitlement SET budget_krw = 300 WHERE id = %s", (ent["id"],))  # 57.6원 × 5 = 288
    results = []
    def worker():
        try:
            results.append(budget.reserve(uid, "chat", INPUT_TOKEN_CAP, ent["id"]))
        except budget.Denied as e:
            results.append(e.reason)
        except Exception as e:  # noqa: BLE001 -- 스레드 안 예외는 조용히 사라지므로 결과에 남긴다
            results.append(f"{type(e).__name__}: {e}")
    ts = [threading.Thread(target=worker) for _ in range(20)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    ok = [r for r in results if isinstance(r, budget.Reservation)]
    e = ent_row()
    check(len(results) == 20 and len(ok) == 5 and results.count("budget") == 15,
          f"예약 성공 {len(ok)}개, 거절 {results.count('budget')}개" + ("" if len(ok) == 5 else f" -- {results[:3]}"))
    check(e["reserved_krw"] == sum(r.worst_krw for r in ok) and e["reserved_krw"] <= 300, f"예약 합계 {e['reserved_krw']} ≤ 300")
    for r in ok:  # 정산 두 번 불러도 한 번만
        budget.settle(r, {"input_tokens": 100, "output_tokens": 10})
        budget.settle(r, {"input_tokens": 100, "output_tokens": 10})
    e = ent_row()
    check(e["reserved_krw"] == 0 and e["spent_krw"] == 5 * budget.actual_cost_krw(get_plan("high"), {"input_tokens": 100, "output_tokens": 10}),
          f"정산은 멱등: reserved 0, spent {e['spent_krw']}")
    PLANS["standard"] = std

    # -------------------------------------------------------------- 6. 결제
    print("\n[6] 결제 (토스 가짜 전송)")
    revoke_all()
    reset_spend()
    os.environ.pop("TOSS_SECRET_KEY", None)
    r = client.post("/api/billing/checkout", json={"plan": "standard"})
    check(r.status_code == 503, f"토스 키 없음 → checkout {r.status_code}")
    r = client.get("/api/billing/me")
    check(r.status_code == 200 and r.json()["payments_enabled"] is False and r.json()["plan"] == "free", "billing/me: 결제 꺼짐, free")
    os.environ["TOSS_SECRET_KEY"] = "test_sk_fake"

    r = client.post("/api/billing/checkout", json={"plan": "standard"})
    check(r.status_code == 200 and r.json()["amount"] == 3900, f"checkout → 주문 {r.json().get('order_id', '')[:12]}… 3,900원")
    order = r.json()
    check(len(order["customer_key"]) >= 20 and order["customer_key"] != f"dm_{uid}", "customer_key 는 해시(사용자 id 그대로가 아님)")

    # 금액 위조
    r = client.post("/api/billing/confirm", json={"payment_key": "pk_" + order["order_id"], "order_id": order["order_id"], "amount": 100})
    check(r.status_code == 400 and not ftoss.calls and ent_row() is None, "금액 위조 → 400, 토스 미호출, 이용권 없음")
    r = client.post("/api/billing/confirm", json={"payment_key": "pk_" + order["order_id"], "order_id": order["order_id"], "amount": 3900})
    check(r.status_code == 409, "닫힌 주문 재승인 → 409")

    # 승인 실패
    order = client.post("/api/billing/checkout", json={"plan": "standard"}).json()
    ftoss.fail_code = "REJECT_CARD_COMPANY"
    r = client.post("/api/billing/confirm", json={"payment_key": "pk_" + order["order_id"], "order_id": order["order_id"], "amount": 3900})
    check(r.status_code == 402 and ent_row() is None, f"승인 실패 → {r.status_code} {r.json()['detail']}, 이용권 없음")
    ftoss.fail_code = None

    # 승인 성공 + 중복 승인
    order = client.post("/api/billing/checkout", json={"plan": "standard"}).json()
    ftoss.calls.clear()
    r = client.post("/api/billing/confirm", json={"payment_key": "pk_" + order["order_id"], "order_id": order["order_id"], "amount": 3900})
    check(r.status_code == 200 and r.json()["plan"] == "standard" and r.json()["ai_budget_left_pct"] == 100, "승인 성공 → Standard 이용권, 예산 100%")
    r2 = client.post("/api/billing/confirm", json={"payment_key": "pk_" + order["order_id"], "order_id": order["order_id"], "amount": 3900})
    with connect() as c:
        n_ent = c.execute("SELECT count(*) AS n FROM entitlement WHERE payment_order_id = %s", (order["order_id"],)).fetchone()["n"]
    check(r2.status_code == 200 and n_ent == 1 and len([x for x in ftoss.calls if x[0] == "POST"]) == 1, "같은 주문 두 번 승인 → 이용권 1개, 토스 승인 1회")
    r = client.get("/api/auth/me")
    check(r.json()["plan"] == "standard" and r.json()["ai_budget_left_pct"] == 100 and r.json()["plan_ends_at"], "auth/me 에 요금제·만료일·남은 %")
    fake.requests.clear()
    res = personal.personal_reco(uid)
    check(res.source == "llm" and len(fake.requests) == 1, "결제 뒤 개인 추천은 LLM")

    # 업그레이드 차단, 같은 요금제 연장
    r = client.post("/api/billing/checkout", json={"plan": "high"})
    check(r.status_code == 409, "Standard 이용 중 High 구매 → 409")
    order2 = client.post("/api/billing/checkout", json={"plan": "standard"}).json()
    r = client.post("/api/billing/confirm", json={"payment_key": "pk_" + order2["order_id"], "order_id": order2["order_id"], "amount": 3900})
    with connect() as c:
        rows = c.execute("SELECT starts_at, ends_at FROM entitlement WHERE user_id = %s AND revoked_at IS NULL ORDER BY starts_at", (uid,)).fetchall()
    check(r.status_code == 200 and len(rows) == 2 and rows[1]["starts_at"] == rows[0]["ends_at"], "연장: 새 이용권이 현재 만료일부터 시작")

    # 환불 웹훅
    ftoss.status = "CANCELED"
    r = client.post("/api/billing/webhook", json={"eventType": "PAYMENT_STATUS_CHANGED", "data": {"paymentKey": "pk_" + order["order_id"], "orderId": order["order_id"], "status": "CANCELED"}})
    check(r.status_code == 200 and r.json()["revoked"] == 1, "환불 웹훅 → 이용권 1개 무효화")
    # 본문의 orderId 를 다른 주문으로 바꿔 보내도 토스 조회 결과와 다르면 무시한다
    r = client.post("/api/billing/webhook", json={"eventType": "PAYMENT_STATUS_CHANGED", "data": {"paymentKey": "pk_" + order["order_id"], "orderId": order2["order_id"], "status": "CANCELED"}})
    check(r.json().get("ignored") is True, "웹훅 본문의 주문번호가 토스 조회와 다르면 무시")
    with connect() as c:
        c.execute("DELETE FROM llm_reco_cache WHERE user_id = %s", (uid,))
        st = c.execute("SELECT status FROM payment WHERE order_id = %s", (order["order_id"],)).fetchone()["status"]
    check(st == "canceled", "결제 기록 status=canceled")
    e = ent_row()
    # 연장분(order2)은 미래 시작이라 지금은 유효한 이용권이 없다 → 무료
    n = len(fake.requests)
    res = personal.personal_reco(uid)
    check(e is None and res.source != "llm" and len(fake.requests) == n, "환불 뒤 LLM 호출 0회")
    ftoss.status = "DONE"

finally:
    with connect() as c:
        c.execute("DELETE FROM llm_spend WHERE user_id = %s", (uid,))
        c.execute("UPDATE entitlement SET payment_order_id = NULL WHERE user_id = %s", (uid,))
        c.execute("DELETE FROM payment WHERE user_id = %s", (uid,))
        c.execute("DELETE FROM app_user WHERE id = %s", (uid,))
    app.dependency_overrides.clear()

print()
if failures:
    print(f"FAILED {len(failures)}:")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("all billing checks passed")
