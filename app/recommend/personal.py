"""로그인 사용자용 개인 추천: 룰로 후보를 좁히고 LLM이 그중에서 고른다.

왜 LLM이 전 메뉴에서 고르게 하지 않나: 4천여 개를 프롬프트에 넣으면 느리고 비싸고,
무엇보다 "한 끼 800kcal 이하" 같은 하드 제약을 모델이 어길 수 있다. 그래서 제약과
채점은 기존 룰(goals.py)이 하고, 모델은 그 결과 중에서 "이 사람에게" 맞는 3개를
고르고 이유를 쓰는 일만 한다. 메뉴명은 후보 enum 으로 강제해 없는 메뉴가 나올 수 없다
(scripts/llm/generate_menu_reco.py 와 같은 방어).

LLM 없이도 개인화는 된다 (personal_rank). 키 없음·타임아웃·거절·형식 오류면 같은 후보를
설정·기록 기반 점수로 다시 줄 세워 source="personal" 로 준다. LLM은 그 위의 선택 사항이다 --
무료 사용자는 personal, (앞으로) 유료 사용자만 llm 이 되도록 갈라 쓸 수 있게 둔 구조다.
source="rule" 은 후보 자체가 없을 때뿐이다.
"""
import hashlib
import json
import os
import random
from collections import Counter
from datetime import datetime, timedelta, timezone

from app.auth import consent
from app.db import connect, get_connection
from app.memory import store as memory
from app.recommend import taste as taste_model
from app.recommend.goals import GOALS
from app.recommend.ranking import diversify, fetch_menus, nearest_stores, rank, to_out
from app.recommend.schemas import PersonalRecoOut

# premium 전용 모델. 후보 표에서 3개 고르고 이유·기억을 쓰는 일이라 최상위 모델까지는 필요 없고,
# 구독료 안에서 호출당 비용을 맞추려고 Sonnet 을 쓴다(운영자 결정). 바꾸면 _input_hash 에 들어가
# 기존 캐시는 자연히 무효가 된다.
MODEL = "claude-sonnet-5"
# 노출 기록에 남기는 추천 방식 버전. 방식이 바뀌면 올려서 운영 지표를 버전별로 가른다.
REC_VERSION = "personal-v1"
# 효과 측정 비교군 비율(%). control 은 지금 규칙 방식을 계속 받는다 -- 학습형이 정말 나은지
# 같은 기간·같은 화면에서 직접 비교하기 위한 몫이다.
CONTROL_PERCENT = 15
IMPRESSION_DEDUPE_SECONDS = 1800
# ponytail: 후보 15개 / 브랜드당 3개. 점수 상위만 자르면 샐러디 15개가 되고, 그러면
# 모델이 고를 게 없다. 브랜드 다양성이 "개인화"의 재료다.
CANDIDATE_LIMIT = 15
PER_BRAND_CAP = 3
PICKS = 3
# 무료 경로는 프롬프트 길이 제약이 없으니 더 넓게 본다 -- 목표 점수는 조금 낮아도 한 끼로는
# 균형이 나은 메뉴가 15위 밖에 있는 경우가 많다(먹태 같은 고단백 사이드가 상위를 채운다).
POOL_LIMIT = 60
CACHE_TTL_SECONDS = 3600
# Lambda 타임아웃이 30초라 그 안에 룰 폴백까지 끝나야 한다. 재시도는 하지 않는다 --
# 재시도로 30초를 넘기느니 룰 결과라도 제때 보여주는 게 낫다.
LLM_TIMEOUT_SECONDS = 20
HISTORY_LIMIT = 200

# 프론트 bmr.js 의 ACTIVITY_FACTORS 와 같은 값. 한 끼 상한을 비워 둔 사용자에게
# 화면과 같은 기준을 적용해야 "목록엔 있는데 AI는 무시" 같은 어긋남이 없다.
ACTIVITY_FACTORS = {"sedentary": 1.2, "light": 1.375, "moderate": 1.55, "active": 1.725}
# 균형 감점의 기준선 -- docs/diet_score.md 와 같은 100kcal당 밀도. 등급과 다른 잣대를 쓰면
# "A등급인데 균형 감점" 같은 모순이 생긴다.
SODIUM_MG_PER_100KCAL = 100  # WHO 1일 2,000mg / 2,000kcal
SUGAR_G_PER_100KCAL = 2.5  # 총에너지 10%
SATFAT_G_PER_100KCAL = 0.78  # 총에너지 7% (AHA)

# ponytail: 개인 점수 가중치. 목표 점수(순위 정규화)가 뼈대이고 나머지는 보정이다 --
# 보정이 뼈대를 이기면 "근성장인데 샐러드 3개" 같은 결과가 나온다. A/B 필요해지면 테이블로.
W_GOAL = 1.0
W_MEAL_FIT = 0.5
W_BALANCE = 0.4
W_BRAND = 0.3
W_SAVED = 0.5
ACTIVITY_LABELS = {"sedentary": "거의 안 움직임", "light": "가벼운 활동", "moderate": "보통 활동", "active": "활발한 활동"}

SYSTEM_PROMPT = """너는 프랜차이즈 메뉴 영양 데이터를 보고 한 사람에게 오늘 한 끼를 골라 주는 영양 코치다.

후보 표에 있는 메뉴만 고를 수 있다. 후보는 이미 그 사람의 하드 제약(한 끼 열량 상한, 음료 제외, 알레르기, 숨긴 메뉴)을 통과한 것들이라 제약을 다시 따질 필요는 없다. 너의 일은 그중에서 이 사람의 목표·신체 조건·최근 선호에 가장 맞는 3개를 서로 다른 성격으로 고르는 것이다 (가능하면 같은 브랜드 3개는 피한다).

reason 은 한국어 한 문장, 60자 이내로 쓴다. 표의 수치를 한두 개 인용해서 왜 이 사람에게 맞는지 말한다. 사람을 부르는 호칭이나 인사말은 넣지 않는다.
comment 는 오늘 식사에 대한 조언을 한국어 1~2문장으로 쓴다. 의학적 진단이나 치료 표현은 쓰지 않는다.

"기억하고 있는 것"은 이 사람에 대해 전에 알아낸 취향이다. 고를 때 반영한다.
new_memories 에는 "최근 뺀 메뉴 / 최근 저장한 메뉴"에서 새로 드러난, 오래 유지될 취향만 0~2개 적는다 (예: "매운 양념 메뉴는 자주 뺀다", "점심은 샐러드를 자주 저장한다"). 한 번뿐인 행동으로 단정하지 않고, 이미 기억하고 있는 것과 같은 내용은 다시 적지 않는다. 한국어 한 줄, 40자 이내, 사실만 쓴다. 건강 상태나 질병을 추측하는 내용은 적지 않는다. 드러난 게 없으면 빈 배열."""


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
    if not row:
        return {}
    # 별도 동의가 없으면 신체정보는 프롬프트(Anthropic, 국외)로 가지 않는다 -- 평균값으로 계산한다.
    return dict(row) if consent.has_health_consent(conn, user_id) else consent.strip_health(dict(row))


def load_history(conn, user_id) -> dict:
    """최근 행동을 요약. hide 는 후보에서 빼고, save/click/ate 는 브랜드 선호로 쓴다."""
    rows = conn.execute(
        """SELECT e.event_type, e.menu_item_id, r.name AS brand, mi.name AS menu
           FROM user_event e
           LEFT JOIN menu_item mi ON mi.id = e.menu_item_id
           LEFT JOIN restaurant r ON r.id = mi.restaurant_id
           WHERE e.user_id = %s
           ORDER BY e.created_at DESC
           LIMIT %s""",
        (user_id, HISTORY_LIMIT),
    ).fetchall()
    hidden = {r["menu_item_id"] for r in rows if r["event_type"] == "hide" and r["menu_item_id"]}
    saved = {r["menu_item_id"] for r in rows if r["event_type"] == "save" and r["menu_item_id"]} - hidden
    liked = Counter(r["brand"] for r in rows if r["event_type"] in ("save", "click", "ate") and r["brand"])
    # 메모리 추출용 최근 행동. 최신순 중복 제거 10개 -- 모델이 "반복"을 보려면 이름이 필요하다.
    recent = lambda kind: list(dict.fromkeys(f"{r['brand']} · {r['menu']}" for r in rows if r["event_type"] == kind and r["menu"]))[:10]
    return {"hidden": hidden, "saved": saved, "liked_brands": [b for b, _ in liked.most_common(5)],
            "recent_hidden": recent("hide"), "recent_saved": recent("save")}


def select_candidates(conn, rows, profile, history, lat, lng, radius_m, limit=CANDIDATE_LIMIT, extra_skip=None):
    """(goal, 후보[(score, reason, row)], nearest). 룰 목록과 같은 채점 + 개인 제약.
    extra_skip(row): 대화에서 말한 조건(분류·브랜드·매운 것…)처럼 호출부가 더하는 제외 규칙."""
    goal = profile.get("goal") if profile.get("goal") in GOALS else "diet"
    limits = {
        "max_calorie": profile.get("max_calorie") or _meal_kcal(profile),
        "max_sodium": profile.get("max_sodium"),
        "max_sugar": None,
    }
    allergies = _split(profile.get("allergies"))

    def skip(row):
        if row["id"] in history["hidden"] or (extra_skip and extra_skip(row)):
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

    return goal, diversify(ranked, PER_BRAND_CAP, limit), nearest


def _balance_excess(n) -> dict:
    """목표 외 영양소가 기준 밀도를 몇 배 넘었는지 {이름: 초과율}. 0 이하(기준 안)는 뺀다."""
    kcal = n.get("calorie")
    if not kcal:
        return {}
    unit = kcal / 100
    out = {}
    for key, limit in (("sodium", SODIUM_MG_PER_100KCAL), ("sugar", SUGAR_G_PER_100KCAL), ("saturated_fat", SATFAT_G_PER_100KCAL)):
        v = n.get(key)
        if v is not None and v / (limit * unit) > 1:
            out[key] = v / (limit * unit) - 1
    return out


def _meal_fit(kcal, target) -> float | None:
    """한 끼 목표 열량 대비 적합도 0~1. 목표의 60~100%면 1 -- 상한은 이미 걸렀으니 넘치는 쪽보다
    "간식 수준이라 한 끼로 모자란" 쪽을 가려내는 게 주 목적이다."""
    if not target or not kcal:
        return None
    r = kcal / target
    if 0.6 <= r <= 1.0:
        return 1.0
    return max(0.0, r / 0.6) if r < 0.6 else max(0.0, 2 - r)


# 조사까지 붙여 둔다 -- "당류은"처럼 받침에 따라 틀리는 걸 코드로 고르느니 3개뿐이라 적는다.
BALANCE_TOPIC = {"sodium": "나트륨은", "sugar": "당류는", "saturated_fat": "포화지방은"}


def personal_rank(goal, candidates, profile, history, taste=None, rng=None):
    """LLM 없이 하는 개인화: [(개인점수, 이유문장, (score, reason, row))] 를 3개, 서로 다른 브랜드로.

    뼈대는 목표 점수(후보 안 순위를 0~1로), 보정은 네 가지:
      한 끼 적합도(신체정보·상한으로 잡은 한 끼 열량에 맞나) / 영양 균형(나트륨·당·포화지방
      초과 감점) / 브랜드 선호(최근 저장·클릭) / 저장한 메뉴.
    신규 사용자도 앞의 둘은 적용되므로 목표 점수 목록과 다른 답이 나온다 -- 기록이 쌓이면
    뒤의 둘이 더해진다.

    taste: 학습형 취향 모델(app/recommend/taste.py). 행동 근거가 있을 때만 켜지고, 켜지면
    위 점수에 학습된 보정(±CLIP)을 더한다. 근거가 없으면(taste.active=False) 결과는 taste 없이
    부른 것과 정확히 같다.

    rng: 있으면 탐색을 켠다 -- 가중치를 사후분포에서 뽑아 채점하고(톰슨 샘플링), 가끔 세 번째 칸을
    고른 적 없는 분류로 채운다. 이유 문장은 샘플이 아니라 사후 평균으로 쓴다(흔들린 값으로 설명하지 않는다).
    """
    learned = taste is not None and taste.active
    target = profile.get("max_calorie") or _meal_kcal(profile)
    # 브랜드 가점은 학습형에서도 둔다. 처음엔 "모델이 브랜드를 배우니 두 번 세지 않게" 뺐는데,
    # 모델은 브랜드를 강하게 규제해서(λ=3) 기록이 적을 땐 거의 못 배운다 -- 저장 한 번에 받던
    # 가점이 사라져 오히려 덜 개인화됐다(검증에서 저장한 메뉴가 다음 추천에서 빠졌다).
    # 학습 보정 전체가 ±CLIP 으로 묶여 있어 겹쳐 세는 폭은 제한된다.
    liked = history["liked_brands"]
    size = max(len(candidates) - 1, 1)
    phis, pool_mean = [], {}
    weights = taste.sample(rng) if learned and rng is not None else None
    if learned:
        phis = [taste.phi(t[2]) for t in candidates]
        for phi in phis:
            for k, v in phi.items():
                pool_mean[k] = pool_mean.get(k, 0.0) + v / len(phis)
    scored = []
    for i, t in enumerate(candidates):
        row = t[2]
        n = row["nutrients"]
        goal_part = 1 - i / size  # 후보는 목표 점수 내림차순 -- goal 마다 점수 척도가 달라 순위로 정규화
        fit = _meal_fit(n.get("calorie"), target)
        excess = _balance_excess(n)
        brand_rank = liked.index(row["restaurant_name"]) if row["restaurant_name"] in liked else None
        saved = row["id"] in history["saved"]

        total = W_GOAL * goal_part - W_BALANCE * min(sum(excess.values()), 2.0)
        if fit is not None:
            total += W_MEAL_FIT * fit
        if brand_rank is not None:
            total += W_BRAND * (1 - brand_rank / len(liked))  # 자주 본 순서대로 가점
        if saved:
            total += W_SAVED
        learned_why = None
        if learned:
            total += taste.score(phis[i], weights)
            learned_why = taste.explain(phis[i], pool_mean)

        # 이유: 목표 수치(t[1]) + 이 사람에게 해당하는 근거 하나. 가장 개인적인 것부터.
        if saved:
            why = "저장해 둔 메뉴"
        elif learned_why:
            why = learned_why
        elif brand_rank is not None:
            why = f"최근 자주 본 {row['restaurant_name']}"
        elif fit == 1.0:
            why = f"한 끼 {target:g}kcal의 {n['calorie'] / target:.0%}"
        elif not excess and n.get("sodium") is not None:
            why = "나트륨·당류·포화지방 모두 기준 안"
        elif excess:
            worst = max(excess, key=excess.get)
            # 고른 이유가 아니라 알고 먹으라는 사실 한 줄 -- goals.py 처럼 평가 대신 수치만.
            why = f"{BALANCE_TOPIC[worst]} 기준의 {excess[worst] + 1:.1f}배"
        else:
            why = None
        scored.append((total, f"{t[1]} · {why}" if why else t[1], t))

    scored.sort(key=lambda x: x[0], reverse=True)
    picks, brands = [], set()
    for item in scored:  # 서로 다른 브랜드 3개 -- 한 브랜드에서 3개면 "추천"이 아니라 "목록"이다
        if item[2][2]["restaurant_id"] in brands:
            continue
        brands.add(item[2][2]["restaurant_id"])
        picks.append(item)
        if len(picks) == PICKS:
            break
    else:
        for item in scored:  # 브랜드가 3개 미만이면 남는 자리는 같은 브랜드로라도 채운다
            if item not in picks:
                picks.append(item)
                if len(picks) == PICKS:
                    break

    # 탐색 칸: 배운 취향만 보여주면 그 밖의 메뉴를 누를 기회가 없어 취향이 바뀌어도 못 배운다.
    # 가끔 세 번째 칸을 고른 적 없는 분류에서 채우고, 그렇다고 문장에 밝힌다(취향 맞춤인 척하지 않는다).
    if learned and rng is not None and len(picks) == PICKS and rng.random() < taste_model.EXPLORE_RATE:
        liked_groups = taste.liked_groups()
        kept_brands = {p[2][2]["restaurant_id"] for p in picks[:-1]}
        for total, _, t in scored:
            row = t[2]
            if (row.get("category_group") or "기타") not in liked_groups and row["restaurant_id"] not in kept_brands:
                picks[-1] = (total, f"{t[1]} · {taste_model.EXPLORE_REASON}", t)
                break
    return picks


def _label(row) -> str:
    # enum 값 겸 표의 메뉴 칸. (restaurant_id, name) 이 UNIQUE 라 브랜드를 붙이면 겹치지 않는다.
    return f"{row['restaurant_name']} · {row['name']}"


def build_prompt(goal, profile, history, candidates, memories=()) -> str:
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
    if history.get("recent_hidden"):
        lines.append(f"최근 뺀 메뉴: {', '.join(history['recent_hidden'])}")
    if history.get("recent_saved"):
        lines.append(f"최근 저장한 메뉴: {', '.join(history['recent_saved'])}")
    lines.append("기억하고 있는 것: " + (" / ".join(memories) if memories else "없음"))

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
            "new_memories": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["picks", "comment", "new_memories"],
        "additionalProperties": False,
    }


def claude_json(system, messages, schema, what) -> dict | None:
    """Claude 에 구조화 출력(JSON)으로 물어본다. 키 없음·실패·거절·형식 오류면 None.

    개인 추천(call_llm)과 대화(app/chat/service.py)가 같이 쓴다 -- 호출 설정과 실패 처리가
    한 곳에 있어야 한쪽만 고쳐져 어긋나는 일이 없다. what 은 로그 구분용.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    import anthropic  # 지연 import: 키 없는 환경(로컬·CI)에서 SDK 없이도 앱이 뜬다

    try:
        client = anthropic.Anthropic(timeout=LLM_TIMEOUT_SECONDS, max_retries=0)
        # 서버 쪽 fallbacks 는 쓰지 않는다 -- Opus 5 용으로 넣었던 기능이고 Sonnet 5 의 허용
        # 대상은 확인되지 않았다(허용 안 되면 요청 전체가 400). 거절(refusal)이 오면 아래에서
        # None 을 돌려 규칙/학습형 추천으로 대체하므로 화면은 비지 않는다.
        response = client.messages.create(
            model=MODEL,
            max_tokens=4000,
            # 후보 표에서 고르고 짧게 답하는 일이라 깊은 추론이 필요 없고, 사용자가 화면 앞에서 기다린다.
            # thinking 은 생략 -- Sonnet 5 는 기본이 adaptive 라 effort 로만 깊이를 조절한다.
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
            system=system,
            messages=messages,
        )
    except anthropic.APIError as e:  # 타임아웃·연결·4xx/5xx 전부 -- 어느 쪽이든 룰로 간다
        print(f"{what} LLM failed: {type(e).__name__}: {e}")
        return None
    if response.stop_reason != "end_turn":  # refusal / max_tokens -- 본문을 믿을 수 없다
        print(f"{what} LLM stop_reason={response.stop_reason}")
        return None
    try:
        return json.loads(next(b.text for b in response.content if b.type == "text"))
    except (StopIteration, json.JSONDecodeError) as e:
        print(f"{what} LLM bad output: {e}")
        return None


def call_llm(prompt, labels) -> dict | None:
    """{"picks": [{menu, reason}], "comment", "new_memories"} 또는 None(키 없음/실패/거절)."""
    return claude_json(SYSTEM_PROMPT, [{"role": "user", "content": prompt}], _schema(labels), "personal reco")


def _input_hash(goal, profile, history, candidates, memories=()) -> str:
    key = {
        "model": MODEL,
        "prompt": SYSTEM_PROMPT,
        "goal": goal,
        "profile": {k: v for k, v in profile.items() if k not in ("user_id", "updated_at")},
        "candidates": [t[2]["id"] for t in candidates],
        "liked": history["liked_brands"],
        "recent": [history.get("recent_hidden"), history.get("recent_saved")],
        "memories": list(memories),
    }
    return hashlib.sha256(json.dumps(key, sort_keys=True, default=str).encode()).hexdigest()


def _cached(conn, user_id, input_hash):
    row = conn.execute(
        """SELECT payload FROM llm_reco_cache
           WHERE user_id = %s AND input_hash = %s AND created_at > now() - make_interval(secs => %s)""",
        (user_id, input_hash, CACHE_TTL_SECONDS),
    ).fetchone()
    return row["payload"] if row else None


def _store_result(user_id, hash_for, payload) -> list[str]:
    """새 메모리 추가 + 캐시 저장을 한 트랜잭션으로. 새로 들어간 메모리를 돌려준다.

    hash_for(메모리 목록) -> 입력 해시. 캐시 키를 "추가한 뒤의" 메모리로 만든다 -- 추가 전
    해시로 저장하면 다음 요청의 메모리 목록이 달라져 캐시를 놓치고, 방금 그 기억을 반영해
    만든 결과를 두고 LLM을 한 번 더 부르게 된다.
    """
    with connect() as conn:
        # 한 번에 2개까지만 받아들인다 -- 프롬프트가 0~2개라고 해도 모델이 넘칠 수 있다.
        added = memory.add_facts(conn, user_id, (payload.get("new_memories") or [])[:2], source="ai")
        input_hash = hash_for([m["fact"] for m in memory.list_facts(conn, user_id)])
        conn.execute(
            """INSERT INTO llm_reco_cache (user_id, input_hash, payload, model, created_at)
               VALUES (%s, %s, %s, %s, now())
               ON CONFLICT (user_id) DO UPDATE
               SET input_hash = EXCLUDED.input_hash, payload = EXCLUDED.payload,
                   model = EXCLUDED.model, created_at = now()""",
            (user_id, input_hash, json.dumps(payload, ensure_ascii=False), MODEL),
        )
    return added


def load_taste(conn, user_id, goal, rows):
    """비교군 ml 사용자의 학습형 취향 모델. control 이면 None(기존 규칙 그대로).
    rows 는 fetch_menus 결과 -- 예시 메뉴의 특징과 영양 밀도 기준을 같은 데이터에서 뽑는다."""
    if variant_for(user_id) != "ml":
        return None
    by_id = {r["id"]: r for r in rows}
    stats = taste_model.density_stats(rows)
    examples = [
        (taste_model.featurize(by_id[mid], stats), y, w, mid)
        for mid, y, w in taste_model.load_examples(conn, user_id)
        if mid in by_id
    ]
    return taste_model.fit(examples, goal, stats)


def hourly_rng(user_id):
    """탐색용 난수. 사용자·날짜·시간으로 시드를 고정해 한 시간 안에는 새로고침해도 같은 3개가 나온다
    (매번 바뀌면 방금 본 메뉴를 다시 찾을 수 없고, 노출 기록도 중복 방지에 안 걸려 부풀려진다)."""
    now = datetime.now(timezone(timedelta(hours=9)))
    return random.Random(f"{user_id}:{now:%Y-%m-%d:%H}")


def variant_for(user_id) -> str:
    """사용자 id 해시로 고정 배정. 매 요청 무작위면 같은 사람이 두 방식을 오가서 비교가 안 된다.
    버전 문자열을 섞어 두면 나중에 실험을 새로 짤 때 배정도 새로 섞인다."""
    h = int(hashlib.sha256(f"{user_id}:{REC_VERSION}".encode()).hexdigest(), 16)
    return "control" if h % 100 < CONTROL_PERCENT else "ml"


def _log_impression(user_id, source, variant, items, scores) -> int | None:
    """보여준 카드 묶음을 남기고 id 를 돌려준다. 실패해도 추천은 나가야 하므로 None 으로 넘어간다.

    같은 사용자에게 같은 묶음이 30분 안에 다시 나가면 새 행을 쓰지 않고 기존 id 를 준다 --
    탭 이동·새로고침·첫 로그인의 연속 조회마다 쓰면 "보여줬는데 무반응"이 부풀려져 학습이
    멀쩡한 메뉴를 싫어하는 것으로 배운다.
    """
    ids = [i.menu_item_id for i in items]
    # 탐색 칸이었는지 -- 운영 지표에서 탐색 칸 참여를 따로 떼어 봐야 학습 효과가 섞이지 않는다.
    explore = [i.reason.endswith(taste_model.EXPLORE_REASON) for i in items]
    try:
        with connect() as conn:
            row = conn.execute(
                """SELECT id FROM reco_impression
                   WHERE user_id = %s AND surface = 'personal_picks' AND menu_item_ids = %s::integer[]
                     AND created_at > now() - make_interval(secs => %s)
                   ORDER BY id DESC LIMIT 1""",
                (user_id, ids, IMPRESSION_DEDUPE_SECONDS),
            ).fetchone()
            if row:
                return row["id"]
            return conn.execute(
                """INSERT INTO reco_impression
                       (user_id, surface, source, variant, model_version, menu_item_ids, scores, explore)
                   VALUES (%s, 'personal_picks', %s, %s, %s, %s::integer[], %s::real[], %s::boolean[]) RETURNING id""",
                (user_id, source, variant,
                 {"llm": MODEL, "ml": taste_model.MODEL_VERSION}.get(source, REC_VERSION), ids, scores, explore),
            ).fetchone()["id"]
    except Exception as e:  # noqa: BLE001 -- 계측 실패가 추천을 막으면 안 된다
        print(f"impression log failed: {type(e).__name__}: {e}")
        return None


def personal_reco(user_id, lat=None, lng=None, radius_m=3000, use_llm=False) -> PersonalRecoOut:
    """use_llm: premium 사용자만 True. free 는 키가 있어도 LLM을 부르지 않는다 -- 무료
    사용자 수만큼 과금이 늘면 안 된다. 어느 쪽이든 결과 칸은 채워진다(personal_rank)."""
    conn = get_connection()
    try:
        profile = load_profile(conn, user_id)
        history = load_history(conn, user_id)
        rows = fetch_menus(conn)
        goal, pool, nearest = select_candidates(
            conn, rows, profile, history, lat, lng, radius_m, limit=POOL_LIMIT
        )
        if not pool:
            return PersonalRecoOut(source="rule", goal=goal, items=[])
        taste = load_taste(conn, user_id, goal, rows)
        # select_candidates 는 목표 점수 순으로 하나씩 담으므로 앞 15개 = limit=15 로 뽑은 결과와 같다.
        candidates = pool[:CANDIDATE_LIMIT]

        # 메모리는 premium 추천만 쓴다 -- free 경로는 규칙 기반이라 읽을 곳이 없다.
        memories = [m["fact"] for m in memory.list_facts(conn, user_id)] if use_llm else []
        input_hash = _input_hash(goal, profile, history, candidates, memories)
        result = _cached(conn, user_id, input_hash) if use_llm else None
    finally:
        conn.close()

    fresh = use_llm and result is None
    if fresh:
        result = call_llm(build_prompt(goal, profile, history, candidates, memories), [_label(t[2]) for t in candidates])

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

    # 비교군: control 은 기존 규칙, ml 은 학습형 취향 모델을 더한다(행동 근거가 있을 때만 --
    # 없으면 둘은 같은 결과라 source 도 personal 로 둔다. "기록으로 학습"이라고 배지를 달았는데
    # 배운 게 없으면 거짓말이다).
    variant = variant_for(user_id)
    if not items:
        picks = personal_rank(goal, pool, profile, history, taste=taste, rng=hourly_rng(user_id))
        source = "ml" if taste is not None and taste.active else "personal"
        out = [to_out(t[0], why, t[2], nearest) for _, why, t in picks]
        impression = _log_impression(user_id, source, variant, out, [round(total, 4) for total, _, _ in picks])
        return PersonalRecoOut(source=source, goal=goal, items=out, impression_id=impression, variant=variant)
    added = []
    if fresh:
        # 실패(None)는 캐시하지 않는다 -- 키를 넣거나 일시 장애가 풀리면 바로 다시 시도해야 한다.
        added = _store_result(
            user_id, lambda mems: _input_hash(goal, profile, history, candidates, mems), result
        )
    impression = _log_impression(user_id, "llm", variant, items, [i.goal_score for i in items])
    return PersonalRecoOut(
        source="llm", goal=goal, comment=result.get("comment"), items=items, memory_added=added,
        impression_id=impression, variant=variant,
    )
