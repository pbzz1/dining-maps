"""대화로 메뉴 찾기.

무료: 문장 -> 조건(parse.py) -> 기존 후보 선택·개인화 랭킹 -> 템플릿 답. LLM 호출 없음.
유료(유효한 이용권, app/billing): 같은 파서로 사용자가 분명히 말한 조건은 확정적으로 걸고(모델이 무시하지
못하게), 그 후보 안에서 Claude(Standard=Haiku 4.5, High=Sonnet 5)가 대화하며 고른다. 대화에서 드러난 취향은
AI 메모리에 쌓는다. 호출마다 이용권 예산에서 최악 비용을 먼저 예약하고, 예산·하루 상한에 걸리면 그 턴은
무료 방식으로 답한다(대화가 끊기지 않게).

서버는 대화도 조건도 저장하지 않는다. 브라우저가 둘 다 들고 매번 보낸다 -- Lambda 는 요청 간
상태가 없고, 대화 내용을 서버에 남기지 않는 편이 개인정보 면에서도 낫다.

답은 스트리밍하지 않는다. Lambda Function URL + Mangum 구성은 응답을 한 번에 돌려주므로,
대신 답을 3문장 이내로 짧게 받아 기다림을 줄인다.
"""
from datetime import datetime, timedelta, timezone

from app.billing import budget
from app.billing.plans import INPUT_TOKEN_CAP
from app.chat import parse as P
from app.chat.schemas import ChatFilters, ChatOut, Chip
from app.db import connect, get_connection
from app.memory import store as memory
from app.menu_category import category_group
from app.recommend.goals import GOALS
from app.recommend.personal import (
    CANDIDATE_LIMIT, PICKS, POOL_LIMIT, _label, _meal_kcal, claude_json, load_history, load_profile,
    hourly_rng, load_taste, personal_rank, select_candidates,
)
from app.recommend.ranking import fetch_menus, to_out

# 하루 상한과 예산은 요금제가 정한다(app/billing/plans.py). 예전의 llm_usage 하루 30회는 이용권 예약으로 대체됐다.
# 모델에 넘기는 이전 대화. 길수록 매 호출 비용이 는다 -- 최근 6턴(사용자·AI 합쳐)이면 맥락은 충분하다.
# 그래도 입력 추정이 INPUT_TOKEN_CAP 을 넘으면 앞 턴부터 더 잘라 맞춘다(넘으면 호출하지 않는다).
HISTORY_TURNS = 6
# 한국은 서머타임이 없어 고정 오프셋이면 된다 -- zoneinfo 는 tz 데이터가 없는 환경(Windows,
# 일부 Lambda 이미지)에서 실패한다.
KST = timezone(timedelta(hours=9))

EXAMPLES = ("매운 거 말고 단백질 많은 거", "700kcal 이하 치킨", "맥날 빼고 버거")

CHAT_SYSTEM = """너는 프랜차이즈 메뉴 영양 데이터를 아는 식사 코치다. 사용자와 한국어로 짧게 대화하며 오늘 먹을 메뉴를 함께 고른다.

메뉴를 추천할 때는 매 턴 주어지는 "후보 표"에 있는 메뉴만 고를 수 있다. 후보는 이미 사용자가 말한 조건과 하드 제약(열량 상한, 알레르기, 숨긴 메뉴)을 통과한 것이다. 표에 맞는 게 없으면 솔직히 없다고 말하고 조건을 어떻게 바꾸면 좋을지 제안한다.

reply 는 3문장 이내로 쓴다. 수치를 인용할 때는 표의 값만 쓴다. picks 는 이번 턴에 새로 추천할 때만 0~3개 채우고, 질문에 답하거나 되묻는 턴이면 비운다. reason 은 한 문장 60자 이내.
의학적 진단이나 치료를 말하지 않는다. 음식과 무관한 요청이면 짧게 답하고 메뉴 이야기로 돌아온다.

new_memories 에는 이번 대화에서 새로 드러난, 오래 유지될 취향만 0~2개 적는다(예: "점심은 회사 근처에서 먹는다"). 한 번뿐인 기분이나 이미 기억한 것은 적지 않는다. 40자 이내, 건강 상태·질병 추측은 적지 않는다."""


def _chat_schema(labels):
    menu = {"type": "string", "enum": labels} if labels else {"type": "string"}
    return {
        "type": "object",
        "properties": {
            "reply": {"type": "string"},
            "picks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"menu": menu, "reason": {"type": "string"}},
                    "required": ["menu", "reason"],
                    "additionalProperties": False,
                },
            },
            "new_memories": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["reply", "picks", "new_memories"],
        "additionalProperties": False,
    }


def effective_profile(profile: dict, f: dict) -> dict:
    """저장된 설정 위에 대화 조건을 얹는다. 대화에서 말한 게 이긴다(그 대화 동안만)."""
    eff = dict(profile)
    for key in ("goal", "max_calorie", "max_sodium"):
        if f[key] is not None:
            eff[key] = f[key]
    if f["exclude_drinks"] is not None:
        eff["exclude_drinks"] = f["exclude_drinks"]
    return eff


def make_skip(f: dict):
    """대화 조건 중 goals 채점이 모르는 것(분류·브랜드·매운 것·재료)을 제외 규칙으로."""
    def skip(row):
        group = row.get("category_group") or category_group(row["category"], row["name"])
        brand, name = row["restaurant_name"], row["name"]
        if f["include_groups"] and group not in f["include_groups"]:
            return True
        if group in f["exclude_groups"]:
            return True
        if f["include_brands"] and brand not in f["include_brands"]:
            return True
        if brand in f["exclude_brands"]:
            return True
        spicy = any(w in name for w in P.SPICY_WORDS)
        if (f["spicy"] == "avoid" and spicy) or (f["spicy"] == "want" and not spicy):
            return True
        return any(w not in name for w in f["include_words"])
    return skip


def _summary(f: dict) -> str:
    return " · ".join(c["label"] for c in P.chips(f))


def _free_reply(understood: bool, f: dict, n_items: int, paid: bool) -> str:
    if not understood:
        hint = "" if paid else " 자유로운 대화는 Standard·High 요금제에서 할 수 있어요."
        return "아직 메뉴 찾는 말만 알아들어요. 예: " + ", ".join(f"'{e}'" for e in EXAMPLES) + "." + hint
    if not n_items:
        return "그 조건에 맞는 메뉴가 없어요. 조건을 하나 지워 보세요."
    summary = _summary(f)
    return f"{summary} 조건으로 골랐어요." if summary else "지금 설정으로 골랐어요."


LIMIT_NOTES = {
    "budget": "이번 기간 AI 사용량을 다 써서 조건 검색으로 답했어요. ",
    "daily": "오늘 AI 대화 {n}회를 다 써서 조건 검색으로 답했어요. ",
    "input": "대화가 너무 길어 조건 검색으로 답했어요. ",
    "no_plan": "이용권이 끝나 조건 검색으로 답했어요. ",
}


def _llm_turn(profile, history_turns, message, f, candidates, memories, plan, user_id, entitlement_id):
    kcal = profile.get("max_calorie") or _meal_kcal(profile)
    fmt = lambda v: "-" if v is None else f"{v:g}"
    ctx = [
        f"목표: {GOALS[profile.get('goal') if profile.get('goal') in GOALS else 'diet']['label']}",
        f"한 끼 열량 상한: {f'{kcal:g}kcal' if kcal else '없음'}",
        f"대화로 정한 조건: {_summary(f) or '없음'}",
        "기억하고 있는 것: " + (" / ".join(memories) if memories else "없음"),
        "",
        f"후보 표 ({len(candidates)}개):",
        "| 메뉴 | 분류 | kcal | 단백질g | 당류g | 나트륨mg | 포화지방g |",
        "|---|---|---|---|---|---|---|",
    ]
    for _, _, r in candidates:
        n = r["nutrients"]
        ctx.append(f"| {_label(r)} | {r.get('category_group') or r['category'] or '-'} | {fmt(n.get('calorie'))} |"
                   f" {fmt(n.get('protein'))} | {fmt(n.get('sugar'))} | {fmt(n.get('sodium'))} | {fmt(n.get('saturated_fat'))} |")
    schema = _chat_schema([_label(t[2]) for t in candidates])
    last = {"role": "user", "content": "[참고 정보]\n" + "\n".join(ctx) + "\n\n[사용자]\n" + message}
    history = [{"role": t.role, "content": t.text} for t in history_turns[-HISTORY_TURNS:]]
    while True:
        # API 는 user 로 시작해야 한다 -- 잘린 기록이 assistant 로 시작하면 앞을 버린다.
        while history and history[0]["role"] != "user":
            history.pop(0)
        messages = history + [last]
        if budget.estimate_input_tokens(CHAT_SYSTEM, messages, schema) <= INPUT_TOKEN_CAP or not history:
            break
        history.pop(0)  # 입력 상한에 맞을 때까지 가장 오래된 턴부터 버린다
    return claude_json(CHAT_SYSTEM, messages, schema, "chat", plan, user_id, entitlement_id)


def chat(user: dict, body) -> ChatOut:
    conn = get_connection()
    try:
        entitlement = budget.active_entitlement(conn, user["id"])
        plan = budget.plan_of(entitlement)
        paid = plan is not None
        profile = load_profile(conn, user["id"])
        history = load_history(conn, user["id"])
        rows = fetch_menus(conn)
        brands = sorted({r["restaurant_name"] for r in rows})
        prev = body.filters.model_dump() if body.filters else None
        if body.remove:
            f, understood = P.remove(prev or P.empty_filters(), body.remove), True
        else:
            f, understood = P.parse(body.message, prev, brands)
        eff = effective_profile(profile, f)
        goal, pool, nearest = select_candidates(
            conn, rows, eff, history, body.lat, body.lng, 3000, limit=POOL_LIMIT, extra_skip=make_skip(f)
        )
        # 무료 대화도 "오늘 당신에겐"과 같은 모델로 고른다(비교군 ml 이면 학습형 취향 포함).
        taste = load_taste(conn, user["id"], goal, rows)
        memories = [m["fact"] for m in memory.list_facts(conn, user["id"])] if paid else []
    finally:
        conn.close()

    def out(reply, source, items, **kw):
        pct = None
        if paid:  # 정산이 끝난 뒤의 남은 예산 -- 화면의 "이번 기간 AI 남은 양"
            c = get_connection()
            try:
                pct = budget.budget_left_pct(budget.active_entitlement(c, user["id"]))
            finally:
                c.close()
        return ChatOut(
            reply=reply, source=source, understood=understood, filters=ChatFilters(**f),
            chips=[Chip(**c) for c in P.chips(f)], items=items, plan=plan.key if plan else "free",
            ai_budget_left_pct=pct, **kw,
        )
    free_items = lambda: [
        to_out(t[0], why, t[2], nearest)
        for _, why, t in personal_rank(goal, pool, eff, history, taste=taste, rng=hourly_rng(user["id"]))
    ]

    # 유료: 메시지가 있으면(칩 지우기만 한 건 제외) 모델에게 묻는다. 파서가 못 알아들은 말도 모델은 안다.
    limit_reason = None
    if paid and body.message.strip() and not body.remove:
        candidates = pool[:CANDIDATE_LIMIT]
        try:
            result = _llm_turn(
                eff, body.history, body.message.strip(), f, candidates, memories, plan, user["id"], entitlement["id"]
            )
        except budget.Denied as e:  # 예산·하루 상한 -- LLM 을 부르지 않았다. 아래 무료 방식으로.
            result, limit_reason = None, e.reason
        if result is not None:
            by_label = {_label(t[2]): t for t in candidates}
            items, seen = [], set()
            for pick in result.get("picks", []):
                t = by_label.get(pick.get("menu"))
                if t and t[2]["id"] not in seen:
                    seen.add(t[2]["id"])
                    items.append(to_out(t[0], pick.get("reason") or t[1], t[2], nearest))
                if len(items) == PICKS:
                    break
            added = []
            if result.get("new_memories"):
                with connect() as c:
                    added = memory.add_facts(c, user["id"], result["new_memories"][:2], source="ai")
            return out(result.get("reply") or "", "llm", items, memory_added=added)

    # 무료, 또는 유료가 예산·상한 초과·실패한 경우
    items = free_items() if (understood or body.remove) else []
    reply = _free_reply(understood, f, len(items), paid)
    if limit_reason:
        reply = LIMIT_NOTES[limit_reason].format(n=plan.daily_limit) + reply
    return out(reply, "filter", items, limit_reached=bool(limit_reason), limit_reason=limit_reason)
