"""로그인 사용자용 개인 추천: 룰로 후보를 좁히고 LLM이 그중에서 고른다.

왜 LLM이 전 메뉴에서 고르게 하지 않나: 4천여 개를 프롬프트에 넣으면 느리고 비싸고,
무엇보다 "한 끼 800kcal 이하" 같은 하드 제약을 모델이 어길 수 있다. 그래서 제약과
채점은 기존 룰(goals.py)이 하고, 모델은 그 결과 중에서 "이 사람에게" 맞는 3개를
고르고 이유를 쓰는 일만 한다. 메뉴명은 후보 enum 으로 강제해 없는 메뉴가 나올 수 없다
(scripts/llm/generate_menu_reco.py 와 같은 방어).

실패는 전부 룰로 떨어진다 -- 키 없음, 타임아웃, 거절, 형식 오류 어느 쪽이든 룰 상위
3개를 source="rule" 로 돌려준다. 개인 추천은 부가 기능이라 이게 화면을 비우면 안 된다.
"""
import hashlib
import json
import os
from collections import Counter

from app.db import connect, get_connection
from app.recommend.goals import GOALS
from app.recommend.ranking import fetch_menus, nearest_stores, rank, to_out
from app.recommend.schemas import PersonalRecoOut

MODEL = "claude-opus-5"
# ponytail: 후보 15개 / 브랜드당 3개. 점수 상위만 자르면 샐러디 15개가 되고, 그러면
# 모델이 고를 게 없다. 브랜드 다양성이 "개인화"의 재료다.
CANDIDATE_LIMIT = 15
PER_BRAND_CAP = 3
PICKS = 3
CACHE_TTL_SECONDS = 3600
# Lambda 타임아웃이 30초라 그 안에 룰 폴백까지 끝나야 한다. 재시도는 하지 않는다 --
# 재시도로 30초를 넘기느니 룰 결과라도 제때 보여주는 게 낫다.
LLM_TIMEOUT_SECONDS = 20
HISTORY_LIMIT = 200

# 프론트 bmr.js 의 ACTIVITY_FACTORS 와 같은 값. 한 끼 상한을 비워 둔 사용자에게
# 화면과 같은 기준을 적용해야 "목록엔 있는데 AI는 무시" 같은 어긋남이 없다.
ACTIVITY_FACTORS = {"sedentary": 1.2, "light": 1.375, "moderate": 1.55, "active": 1.725}
ACTIVITY_LABELS = {"sedentary": "거의 안 움직임", "light": "가벼운 활동", "moderate": "보통 활동", "active": "활발한 활동"}

SYSTEM_PROMPT = """너는 프랜차이즈 메뉴 영양 데이터를 보고 한 사람에게 오늘 한 끼를 골라 주는 영양 코치다.

후보 표에 있는 메뉴만 고를 수 있다. 후보는 이미 그 사람의 하드 제약(한 끼 열량 상한, 음료 제외, 알레르기, 숨긴 메뉴)을 통과한 것들이라 제약을 다시 따질 필요는 없다. 너의 일은 그중에서 이 사람의 목표·신체 조건·최근 선호에 가장 맞는 3개를 서로 다른 성격으로 고르는 것이다 (가능하면 같은 브랜드 3개는 피한다).

reason 은 한국어 한 문장, 60자 이내로 쓴다. 표의 수치를 한두 개 인용해서 왜 이 사람에게 맞는지 말한다. 사람을 부르는 호칭이나 인사말은 넣지 않는다.
comment 는 오늘 식사에 대한 조언을 한국어 1~2문장으로 쓴다. 의학적 진단이나 치료 표현은 쓰지 않는다."""


def _meal_kcal(profile) -> int | None:
    """Mifflin-St Jeor 로 하루 필요량 -> 3끼로 나눈 값. frontend bmr.js perMealCalorie 와 같은 식."""
    h, w, a = profile.get("height_cm"), profile.get("weight_kg"), profile.get("age")
    if not (h and w and a):
        return None
    bmr = 10 * w + 6.25 * h - 5 * a + (-161 if profile.get("sex") == "female" else 5)
    return round(bmr * ACTIVITY_FACTORS.get(profile.get("activity"), 1.2) / 3)


def _split(csv: str | None) -> list[str]:
    return [t.strip() for t in (csv or "").split(",") if t.strip()]


def load_profile(conn, user_id) -> dict:
    row = conn.execute("SELECT * FROM user_profile WHERE user_id = %s", (user_id,)).fetchone()
    return dict(row) if row else {}


def load_history(conn, user_id) -> dict:
    """최근 행동을 요약. hide 는 후보에서 빼고, save/click/ate 는 브랜드 선호로 쓴다."""
    rows = conn.execute(
        """SELECT e.event_type, e.menu_item_id, r.name AS brand
           FROM user_event e
           LEFT JOIN menu_item mi ON mi.id = e.menu_item_id
           LEFT JOIN restaurant r ON r.id = mi.restaurant_id
           WHERE e.user_id = %s
           ORDER BY e.created_at DESC
           LIMIT %s""",
        (user_id, HISTORY_LIMIT),
    ).fetchall()
    hidden = {r["menu_item_id"] for r in rows if r["event_type"] == "hide" and r["menu_item_id"]}
    liked = Counter(r["brand"] for r in rows if r["event_type"] in ("save", "click", "ate") and r["brand"])
    return {"hidden": hidden, "liked_brands": [b for b, _ in liked.most_common(5)]}


def select_candidates(conn, rows, profile, history, lat, lng, radius_m):
    """(goal, 후보[(score, reason, row)], nearest). 룰 목록과 같은 채점 + 개인 제약."""
    goal = profile.get("goal") if profile.get("goal") in GOALS else "diet"
    limits = {
        "max_calorie": profile.get("max_calorie") or _meal_kcal(profile),
        "max_sodium": profile.get("max_sodium"),
        "max_sugar": None,
    }
    allergies = _split(profile.get("allergies"))

    def skip(row):
        if row["id"] in history["hidden"]:
            return True
        # 알레르기 정보가 공개된 메뉴만 판정할 수 있다. 미공개(None)는 걸러내지 않고
        # 프롬프트 표에 "미공개"로 드러내 모델이 알게 한다 -- 전부 빼면 후보가 거의 안 남는다.
        info = row["allergy_info"] or ""
        return any(a in info for a in allergies)

    ranked = rank(rows, goal, limits, bool(profile.get("exclude_drinks")), skip)

    nearest = {}
    if lat is not None and lng is not None:
        nearest = nearest_stores(conn, {t[2]["restaurant_id"] for t in ranked}, lat, lng, radius_m)
        nearby = [t for t in ranked if t[2]["restaurant_id"] in nearest]
        # 근처에 고를 만한 게 너무 적으면 반경 제한을 풀어 준다 -- 빈 카드보다 먼 추천이 낫다.
        if len(nearby) >= PICKS:
            ranked = nearby

    per_brand, picked = Counter(), []
    for t in ranked:
        brand = t[2]["restaurant_id"]
        if per_brand[brand] >= PER_BRAND_CAP:
            continue
        per_brand[brand] += 1
        picked.append(t)
        if len(picked) == CANDIDATE_LIMIT:
            break
    return goal, picked, nearest


def _label(row) -> str:
    # enum 값 겸 표의 메뉴 칸. (restaurant_id, name) 이 UNIQUE 라 브랜드를 붙이면 겹치지 않는다.
    return f"{row['restaurant_name']} · {row['name']}"


def build_prompt(goal, profile, history, candidates) -> str:
    fmt = lambda v: "-" if v is None else f"{v:g}"
    kcal = profile.get("max_calorie") or _meal_kcal(profile)
    who = []
    if profile.get("sex"):
        who.append("여성" if profile["sex"] == "female" else "남성")
    if profile.get("age"):
        who.append(f"{profile['age']}세")
    if profile.get("height_cm") and profile.get("weight_kg"):
        who.append(f"{profile['height_cm']:g}cm/{profile['weight_kg']:g}kg")
    if profile.get("activity") in ACTIVITY_LABELS:
        who.append(ACTIVITY_LABELS[profile["activity"]])

    lines = [
        f"목표: {GOALS[goal]['label']}",
        f"신체 정보: {', '.join(who) if who else '입력 안 함'}",
        f"한 끼 열량 상한: {f'{kcal:g}kcal' if kcal else '없음'}",
    ]
    if profile.get("max_sodium"):
        lines.append(f"한 끼 나트륨 상한: {profile['max_sodium']:g}mg")
    if profile.get("dislikes"):
        lines.append(f"싫어하는 것(본인 입력): {profile['dislikes']}")
    if profile.get("allergies"):
        lines.append(f"알레르기(본인 입력): {profile['allergies']} -- 공개된 알레르기 정보로는 이미 걸렀다")
    if history["liked_brands"]:
        lines.append(f"최근 자주 본 브랜드: {', '.join(history['liked_brands'])}")

    table = ["| 메뉴 | 분류 | kcal | 단백질g | 당류g | 나트륨mg | 포화지방g | 알레르기 |", "|---|---|---|---|---|---|---|---|"]
    for _, _, r in candidates:
        n = r["nutrients"]
        table.append(
            f"| {_label(r)} | {r['category'] or '-'} | {fmt(n.get('calorie'))} | {fmt(n.get('protein'))} |"
            f" {fmt(n.get('sugar'))} | {fmt(n.get('sodium'))} | {fmt(n.get('saturated_fat'))} |"
            f" {r['allergy_info'] or '미공개'} |"
        )
    return "\n".join(lines) + f"\n\n후보 {len(candidates)}개 (목표 기준 점수 높은 순):\n" + "\n".join(table)


def _schema(labels):
    return {
        "type": "object",
        "properties": {
            "picks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "menu": {"type": "string", "enum": labels},
                        "reason": {"type": "string"},
                    },
                    "required": ["menu", "reason"],
                    "additionalProperties": False,
                },
            },
            "comment": {"type": "string"},
        },
        "required": ["picks", "comment"],
        "additionalProperties": False,
    }


def call_llm(prompt, labels) -> dict | None:
    """{"picks": [{menu, reason}], "comment"} 또는 None(키 없음/실패/거절)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    import anthropic  # 지연 import: 키 없는 환경(로컬·CI)에서 SDK 없이도 앱이 뜬다

    try:
        client = anthropic.Anthropic(timeout=LLM_TIMEOUT_SECONDS, max_retries=0)
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=4000,
            # 후보 15개 중 3개 고르기는 깊은 추론이 필요 없고, 사용자가 화면 앞에서 기다린다.
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": _schema(labels)}},
            # 안전 분류기가 거절하면 서버가 다른 모델로 재시도한다 (거절 카테고리별 자동 선택).
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError as e:  # 타임아웃·연결·4xx/5xx 전부 -- 어느 쪽이든 룰로 간다
        print(f"personal reco LLM failed: {type(e).__name__}: {e}")
        return None
    if response.stop_reason != "end_turn":  # refusal / max_tokens -- 본문을 믿을 수 없다
        print(f"personal reco LLM stop_reason={response.stop_reason}")
        return None
    try:
        return json.loads(next(b.text for b in response.content if b.type == "text"))
    except (StopIteration, json.JSONDecodeError) as e:
        print(f"personal reco LLM bad output: {e}")
        return None


def _input_hash(goal, profile, history, candidates) -> str:
    key = {
        "model": MODEL,
        "prompt": SYSTEM_PROMPT,
        "goal": goal,
        "profile": {k: v for k, v in profile.items() if k not in ("user_id", "updated_at")},
        "candidates": [t[2]["id"] for t in candidates],
        "liked": history["liked_brands"],
    }
    return hashlib.sha256(json.dumps(key, sort_keys=True, default=str).encode()).hexdigest()


def _cached(conn, user_id, input_hash):
    row = conn.execute(
        """SELECT payload FROM llm_reco_cache
           WHERE user_id = %s AND input_hash = %s AND created_at > now() - make_interval(secs => %s)""",
        (user_id, input_hash, CACHE_TTL_SECONDS),
    ).fetchone()
    return row["payload"] if row else None


def _store_cache(user_id, input_hash, payload):
    with connect() as conn:
        conn.execute(
            """INSERT INTO llm_reco_cache (user_id, input_hash, payload, model, created_at)
               VALUES (%s, %s, %s, %s, now())
               ON CONFLICT (user_id) DO UPDATE
               SET input_hash = EXCLUDED.input_hash, payload = EXCLUDED.payload,
                   model = EXCLUDED.model, created_at = now()""",
            (user_id, input_hash, json.dumps(payload, ensure_ascii=False), MODEL),
        )


def personal_reco(user_id, lat=None, lng=None, radius_m=3000) -> PersonalRecoOut:
    conn = get_connection()
    try:
        profile = load_profile(conn, user_id)
        history = load_history(conn, user_id)
        goal, candidates, nearest = select_candidates(
            conn, fetch_menus(conn), profile, history, lat, lng, radius_m
        )
        if not candidates:
            return PersonalRecoOut(source="rule", goal=goal, items=[])

        input_hash = _input_hash(goal, profile, history, candidates)
        result = _cached(conn, user_id, input_hash)
    finally:
        conn.close()

    fresh = result is None
    if fresh:
        result = call_llm(build_prompt(goal, profile, history, candidates), [_label(t[2]) for t in candidates])

    by_label = {_label(t[2]): t for t in candidates}
    items, seen = [], set()
    for pick in (result or {}).get("picks", []):
        t = by_label.get(pick.get("menu"))
        if not t or t[2]["id"] in seen:  # enum 이 막아 주지만 중복 선택까지는 못 막는다
            continue
        seen.add(t[2]["id"])
        items.append(to_out(t[0], pick.get("reason") or t[1], t[2], nearest))
        if len(items) == PICKS:
            break

    if not items:
        top = candidates[:PICKS]
        return PersonalRecoOut(
            source="rule", goal=goal, items=[to_out(s, r, row, nearest) for s, r, row in top]
        )
    if fresh:
        # 실패(None)는 캐시하지 않는다 -- 키를 넣거나 일시 장애가 풀리면 바로 다시 시도해야 한다.
        _store_cache(user_id, input_hash, result)
    return PersonalRecoOut(source="llm", goal=goal, comment=result.get("comment"), items=items)
