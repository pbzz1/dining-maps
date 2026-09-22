"""무료 "대화형 필터": 문장을 추천 조건으로 바꾼다. LLM 없이 규칙·사전만 쓴다.

자유 대화를 알아듣는 게 목표가 아니다. "매운 거 말고 단백질 많은 거", "700kcal 이하 치킨",
"맥날 빼고"처럼 메뉴를 찾는 말만 조건으로 바꾸고, 못 알아들은 건 못 알아들었다고 말한다
(understood=False) -- 모르는 문장을 억지로 해석해 엉뚱한 조건을 거는 게 제일 나쁘다.

조건은 누적된다. 이전 조건(filters)에 이번 문장이 말한 것만 덮어쓴다 -- "치킨" 다음에
"700kcal 이하"라고 하면 둘 다 걸린다. 같은 대상을 반대로 말하면(포함 <-> 제외) 나중 말이 이긴다.

DB·프레임워크 의존이 없는 순수 함수라 아래 __main__ 에서 바로 검사한다.
"""
import re

GOAL_LABELS = {"diet": "다이어트", "protein": "근성장", "low_sodium": "저나트륨"}

# 사용자가 부르는 말 -> app/menu_category.py GROUPS. 긴 말부터 맞춘다(감자튀김 > 감자).
GROUP_WORDS = {
    "햄버거": "버거", "버거": "버거", "와퍼": "버거",
    "치킨": "치킨", "통닭": "치킨", "윙": "치킨",
    "피자": "피자",
    "샐러드": "샐러드·샌드위치", "샌드위치": "샐러드·샌드위치", "포케": "샐러드·샌드위치", "샌드": "샐러드·샌드위치",
    "음료수": "음료", "음료": "음료", "커피": "음료", "라떼": "음료", "마실": "음료",
    "디저트": "디저트", "케이크": "디저트", "케익": "디저트", "아이스크림": "디저트", "도넛": "디저트",
    "빵": "디저트", "달달한": "디저트", "단 거": "디저트", "단것": "디저트",
    "감자튀김": "사이드", "감튀": "사이드", "사이드": "사이드",
}

# 흔한 줄임말. 정식 이름(브랜드 목록)은 호출부가 DB에서 넘긴다.
BRAND_ALIASES = {
    "맥날": "맥도날드", "맥도널드": "맥도날드", "롯리": "롯데리아", "스벅": "스타벅스", "버킹": "버거킹",
    "교촌": "교촌치킨", "도미노": "도미노피자", "파바": "파리바게뜨", "파리바게트": "파리바게뜨",
    "배라": "배스킨라빈스", "베라": "배스킨라빈스", "맘터": "맘스터치", "비에이치씨": "BHC", "bhc": "BHC",
    "한솥": "한솥도시락", "파파존스": "파파존스", "미피": "미스터피자", "뚜쥬": "뚜레쥬르",
}

# 메뉴 이름에 이게 있으면 맵다고 본다. '핫'은 핫도그·핫케익·핫초코를 잡아서 뺐다.
SPICY_WORDS = ("매운", "매콤", "불닭", "청양", "스파이시", "마라", "고추", "볼케이노", "핫윙", "떡볶이", "불맛")

# 이름으로 찾는 식재료. 분류(치킨)와 다르다 -- "닭가슴살"은 샐러드·샌드위치에 더 많다.
NAME_WORDS = ("닭가슴살", "연어", "새우", "두부", "베이컨", "불고기", "치즈", "참치", "아보카도", "에그", "달걀", "계란")

NEG_AFTER = ("말고", "빼고", "빼줘", "빼", "제외", "싫", "안 먹", "안먹", "아닌", "없는", "말구", "노노", "별로")
NEG_BEFORE = ("안 ", "안", "덜 ", "덜")

RESET_WORDS = ("초기화", "처음부터", "리셋", "다시 시작", "조건 다 지워", "전부 지워")

KCAL_RE = re.compile(r"(\d{2,4})\s*(?:kcal|칼로리|키로|킬로칼로리|㎉)\s*(이하|아래|미만|까지|안쪽|이내|이상|넘는|초과)?", re.I)
SODIUM_RE = re.compile(r"나트륨\s*(\d{2,4})\s*(?:mg|밀리)?\s*(이하|아래|미만|까지|이내)?", re.I)

EMPTY = {
    "goal": None, "max_calorie": None, "max_sodium": None, "exclude_drinks": None,
    "include_groups": [], "exclude_groups": [], "include_brands": [], "exclude_brands": [],
    "include_words": [], "spicy": None,
}


def empty_filters() -> dict:
    return {k: (list(v) if isinstance(v, list) else v) for k, v in EMPTY.items()}


def _negated(text: str, start: int, end: int) -> bool:
    """[start,end) 에 있는 말이 부정됐나. 뒤 8자 안의 '말고/빼고…' 또는 바로 앞의 '안/덜'."""
    after = text[end:end + 8]
    before = text[max(0, start - 2):start]
    return any(after.lstrip().startswith(w) or f" {w}" in after[:6] or after.startswith(w) for w in NEG_AFTER) \
        or any(before.endswith(w) for w in NEG_BEFORE)


def _toggle(f: dict, inc: str, exc: str, value: str, negative: bool):
    """포함/제외 목록 한 쌍에서 value 를 한쪽으로 옮긴다(나중 말이 이긴다)."""
    add, remove = (exc, inc) if negative else (inc, exc)
    if value in f[remove]:
        f[remove].remove(value)
    if value not in f[add]:
        f[add].append(value)


def _find(text: str, words) -> list[tuple[str, int, int]]:
    """겹치지 않게, 긴 말 먼저 찾는다 -> [(단어, 시작, 끝)]."""
    taken, hits = [False] * len(text), []
    for w in sorted(words, key=len, reverse=True):
        for m in re.finditer(re.escape(w), text):
            if any(taken[m.start():m.end()]):
                continue
            taken[m.start():m.end()] = [True] * (m.end() - m.start())
            hits.append((w, m.start(), m.end()))
    return sorted(hits, key=lambda h: h[1])


def parse(message: str, filters: dict | None, brands: list[str]) -> tuple[dict, bool]:
    """(새 조건, 알아들은 게 있나). filters 는 이전 대화까지의 조건(없으면 빈 조건)."""
    f = empty_filters()
    for k, v in (filters or {}).items():
        if k in f:
            f[k] = list(v) if isinstance(v, list) else v
    text = " ".join((message or "").split())
    low = text.lower()
    understood = False

    if any(w in text for w in RESET_WORDS):
        return empty_filters(), True

    # --- 목표 -------------------------------------------------------------
    if re.search(r"단백질|고단백|근육|벌크|근성장|헬스|운동", text) and "단백질 적" not in text:
        f["goal"], understood = "protein", True
    if re.search(r"짜지 ?않|안 ?짠|싱거|저염|저나트륨|나트륨 ?(적|낮)|덜 ?짠", text):
        f["goal"], understood = "low_sodium", True
    if re.search(r"다이어트|살 ?빼|살 ?안 ?찌|체중|칼로리 ?(낮|적)|저칼로리", text):
        f["goal"], understood = "diet", True

    # --- 숫자 상한 --------------------------------------------------------
    for m in KCAL_RE.finditer(low):
        if m.group(2) in ("이상", "넘는", "초과"):
            continue  # 하한은 지원하지 않는다 -- 상한으로 잘못 걸면 반대 결과가 나온다
        f["max_calorie"], understood = float(m.group(1)), True
    if f["max_calorie"] is None and re.search(r"가볍게|가벼운|가볍고|라이트|간단히", text):
        f["max_calorie"], understood = 500.0, True
    for m in SODIUM_RE.finditer(low):
        f["max_sodium"], understood = float(m.group(1)), True

    # --- 브랜드 -----------------------------------------------------------
    names = {b.lower(): b for b in brands}
    names.update({a.lower(): b for a, b in BRAND_ALIASES.items() if b in brands})
    # 브랜드 이름 안에 분류 단어가 들어 있다(교촌'치킨', 도미노'피자') -- 그 자리는 분류로 다시 읽지 않는다.
    brand_spans = []
    for w, s, e in _find(low, names):
        _toggle(f, "include_brands", "exclude_brands", names[w], _negated(low, s, e))
        brand_spans.append((s, e))
        understood = True

    # --- 분류 -------------------------------------------------------------
    for w, s, e in _find(text, GROUP_WORDS):
        if any(bs <= s < be for bs, be in brand_spans):
            continue
        group, neg = GROUP_WORDS[w], _negated(text, s, e)
        _toggle(f, "include_groups", "exclude_groups", group, neg)
        if group == "음료":
            f["exclude_drinks"] = neg  # 음료를 달라면 "음료 제외" 설정을 이번엔 푼다
        understood = True

    # --- 매운 것 -----------------------------------------------------------
    spicy = re.search(r"(안 ?|덜 ?)?(맵|매운|매콤|얼큰)(지 ?않|지 ?말|지 ?않은)?", text)
    if spicy:
        neg = bool(spicy.group(1) or spicy.group(3)) or _negated(text, spicy.start(), spicy.end() + 2)
        f["spicy"], understood = ("avoid" if neg else "want"), True

    # --- 이름 재료 ---------------------------------------------------------
    for w, s, e in _find(text, NAME_WORDS):
        if _negated(text, s, e):
            if w in f["include_words"]:
                f["include_words"].remove(w)
            continue
        if w not in f["include_words"]:
            f["include_words"].append(w)
        understood = True

    return f, understood


def chips(f: dict) -> list[dict]:
    """조건을 사람이 읽는 칩으로. key 는 지울 때 서버로 되돌려 보내는 식별자."""
    out = []
    if f["goal"]:
        out.append({"key": "goal", "label": GOAL_LABELS[f["goal"]]})
    out += [{"key": f"group:{g}", "label": g} for g in f["include_groups"]]
    out += [{"key": f"xgroup:{g}", "label": f"{g} 제외"} for g in f["exclude_groups"]]
    out += [{"key": f"brand:{b}", "label": b} for b in f["include_brands"]]
    out += [{"key": f"xbrand:{b}", "label": f"{b} 제외"} for b in f["exclude_brands"]]
    out += [{"key": f"word:{w}", "label": w} for w in f["include_words"]]
    if f["spicy"]:
        out.append({"key": "spicy", "label": "매운 메뉴" if f["spicy"] == "want" else "매운 메뉴 제외"})
    if f["max_calorie"]:
        out.append({"key": "kcal", "label": f"{f['max_calorie']:g}kcal 이하"})
    if f["max_sodium"]:
        out.append({"key": "sodium", "label": f"나트륨 {f['max_sodium']:g}mg 이하"})
    return out


def remove(f: dict, key: str) -> dict:
    """칩 하나 지우기. 모르는 key 는 무시한다."""
    f = {k: (list(v) if isinstance(v, list) else v) for k, v in f.items()}
    kind, _, value = key.partition(":")
    lists = {"group": "include_groups", "xgroup": "exclude_groups", "brand": "include_brands",
             "xbrand": "exclude_brands", "word": "include_words"}
    if kind in lists and value in f[lists[kind]]:
        f[lists[kind]].remove(value)
        if value == "음료" and kind in ("group", "xgroup"):
            f["exclude_drinks"] = None
    elif kind in ("goal", "spicy"):
        f[kind] = None
    elif kind == "kcal":
        f["max_calorie"] = None
    elif kind == "sodium":
        f["max_sodium"] = None
    return f


if __name__ == "__main__":
    B = ["BHC", "교촌치킨", "맥도날드", "서브웨이", "샐러디", "스타벅스", "도미노피자", "버거킹"]
    p = lambda msg, prev=None: parse(msg, prev, B)

    f, ok = p("매운 거 말고 단백질 많은 거")
    assert ok and f["goal"] == "protein" and f["spicy"] == "avoid", f
    f, _ = p("안 매운 걸로")
    assert f["spicy"] == "avoid"
    f, _ = p("맵지 않은 메뉴")
    assert f["spicy"] == "avoid", f
    f, _ = p("매콤한 거 먹고 싶어")
    assert f["spicy"] == "want"

    f, ok = p("700kcal 이하 치킨")
    assert ok and f["max_calorie"] == 700 and f["include_groups"] == ["치킨"], f
    f, _ = p("500칼로리 아래로")
    assert f["max_calorie"] == 500
    f, _ = p("800kcal 이상")
    assert f["max_calorie"] is None  # 하한은 상한으로 잘못 걸지 않는다

    f, _ = p("음료 빼고 샐러드")
    assert f["exclude_groups"] == ["음료"] and f["include_groups"] == ["샐러드·샌드위치"] and f["exclude_drinks"] is True, f
    f, _ = p("커피 추천해줘")
    assert f["include_groups"] == ["음료"] and f["exclude_drinks"] is False

    f, _ = p("맥날 빼고 버거")
    assert f["exclude_brands"] == ["맥도날드"] and f["include_groups"] == ["버거"], f
    f, _ = p("교촌치킨에서 뭐 먹지")
    assert f["include_brands"] == ["교촌치킨"] and f["include_groups"] == [], f  # 브랜드명 속 '치킨'은 분류 아님
    f, _ = p("bhc 말고")
    assert f["exclude_brands"] == ["BHC"]

    # 누적: 이전 조건 위에 덮어쓴다
    f1, _ = p("치킨")
    f2, _ = p("700kcal 이하", f1)
    assert f2["include_groups"] == ["치킨"] and f2["max_calorie"] == 700
    f3, _ = p("치킨 말고 버거", f2)
    assert f3["include_groups"] == ["버거"] and f3["exclude_groups"] == ["치킨"], f3  # 나중 말이 이긴다
    f4, ok = p("처음부터 다시", f3)
    assert ok and f4 == empty_filters()

    f, _ = p("나트륨 800mg 이하")
    assert f["max_sodium"] == 800
    f, _ = p("짜지 않은 걸로")
    assert f["goal"] == "low_sodium"
    f, _ = p("다이어트 중이야 가볍게")
    assert f["goal"] == "diet" and f["max_calorie"] == 500
    f, _ = p("닭가슴살 들어간 거")
    assert f["include_words"] == ["닭가슴살"]

    f, ok = p("오늘 날씨 좋네")
    assert not ok and f == empty_filters()  # 모르는 말은 모른다고

    # 칩 지우기
    f, _ = p("치킨 말고 700kcal 이하 매운 거 말고")
    labels = [c["label"] for c in chips(f)]
    assert labels == ["치킨 제외", "매운 메뉴 제외", "700kcal 이하"], labels
    g = remove(f, "kcal")
    assert g["max_calorie"] is None and g["exclude_groups"] == ["치킨"] and f["max_calorie"] == 700  # 원본 불변
    assert remove(f, "xgroup:치킨")["exclude_groups"] == []
    assert remove(f, "nope:x") == f
    print("ok")
