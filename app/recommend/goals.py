"""목표(goal)별 메뉴 점수 규칙. 로그인/신체정보 없이 '목표 선택'만으로 개인화한다.

각 goal 은 (필요한 영양소, 점수 함수, 추천 이유 문구) 세 개로 정의된다.
점수는 '높을수록 좋음'으로 통일하고, 필요한 영양소가 빠진 메뉴는 제외한다
(결측을 0 으로 보면 저칼로리로 오인돼 1등에 올라오는 사고가 난다).

ponytail: 가중치는 상수. A/B 테스트가 필요해지면 그때 테이블로 뺀다.
"""
import re

GOALS = {
    "diet": {
        "label": "다이어트",
        "requires": ("calorie",),
        # diet_score 가 이미 WHO 기준 종합 점수라 그대로 쓴다 (None 이면 제외).
        "score": lambda n, diet_score: diet_score,
        "reason": lambda n, diet_score: f"{n['calorie']:.0f}kcal · 다이어트 점수 {diet_score:.0f}/100",
    },
    "protein": {
        "label": "근성장",
        "requires": ("calorie", "protein"),
        # 100kcal 당 단백질 g. 절대량으로 하면 그냥 큰 메뉴가 이긴다.
        "score": lambda n, _: n["protein"] / n["calorie"] * 100,
        "reason": lambda n, _: f"단백질 {n['protein']:.0f}g / {n['calorie']:.0f}kcal",
    },
    "low_sodium": {
        "label": "저나트륨",
        "requires": ("calorie", "sodium", "sugar"),
        "score": lambda n, _: -n["sodium"],
        # WHO 1일 권장 2000mg 대비 비율 -- "좋다"는 주장 대신 사실만 적는다.
        "reason": lambda n, _: f"나트륨 {n['sodium']:.0f}mg (WHO 1일 권장량의 {n['sodium'] / 2000 * 100:.0f}%)",
    },
}

# 하드 제약: 점수 매기기 전에 먼저 걸러낸다. 쿼리 파라미터 이름 -> 영양소.
LIMITS = {"max_calorie": "calorie", "max_sodium": "sodium", "max_sugar": "sugar"}
MIN_CALORIE = 100

# ponytail: category 값이 브랜드마다 제각각(130종)이라 정규화 대신 키워드로 음료를 판별한다.
# 카테고리 정규화 컬럼이 생기면 그걸로 교체.
DRINK_KEYWORDS = ("음료", "커피", "에스프레소", "라떼", "브루", "프라푸치노", "블렌디드", "주스",
                  "스무디", "스파클링", "피지오", "아이스샷", "리프레셔", "쉐이크", "아메리카노", "초코",
                  "드링크", "소다", "빙수", "할리치노")

# "티"(차)만 한 글자라 부분일치로 쓰면 패**티**·스파게**티**·로**티**세리·**티**라미수·그린**티**가
# 전부 음료로 잡힌다 (실제로 도미노 피자 23개가 음료 기준으로 채점되고 있었다). 앞뒤가 한글이
# 아닐 때만 "티"로 인정한다 -- 스타벅스 "티(티바나)"·커피빈 "티" 카테고리와 "... 블랙 티" 같은
# 이름은 그대로 잡히고, 위 오탐 36건은 전부 빠진다.
DRINK_TEA_RE = re.compile(r"(?<![가-힣])티(?![가-힣])")


def is_drink(category: str | None, name: str) -> bool:
    text = f"{category or ''} {name}"
    return any(k in text for k in DRINK_KEYWORDS) or bool(DRINK_TEA_RE.search(text))


def score_item(goal: str, nutrients: dict, diet_score, limits: dict, drink: bool = False):
    """해당 goal 로 점수를 낼 수 있으면 (score, reason), 아니면 None."""
    g = GOALS[goal]
    # 음료는 diet 에서만 (음료 기준 diet_score 가 있음). 비율 goal 은 5kcal 음료가 1등을 하므로 제외.
    if drink and goal != "diet":
        return None
    if any(k not in nutrients for k in g["requires"]):
        return None
    if goal == "diet" and diet_score is None:
        return None
    # diet_score 와 같은 기준: 100kcal 미만(차/아메리카노)은 '한 끼'가 아니라 제외.
    # 안 하면 비율 기반 goal 에서 3kcal 차가 단백질 1등을 한다.
    if not drink and nutrients["calorie"] < MIN_CALORIE:
        return None
    # 저나트륨은 나트륨만 보면 케이크·아이스크림이 1등을 한다 -- 당류가 WHO 상한
    # (총에너지 10%E = 2.5g/100kcal, docs/diet_score.md) 이내인 메뉴만 남긴다.
    if goal == "low_sodium" and nutrients["sugar"] > nutrients["calorie"] * 0.025:
        return None
    for param, nutrient in LIMITS.items():
        cap = limits.get(param)
        # 상한이 걸렸는데 값이 없으면 모른다 -> 보수적으로 제외.
        if cap is not None and (nutrient not in nutrients or nutrients[nutrient] > cap):
            return None
    return g["score"](nutrients, diet_score), g["reason"](nutrients, diet_score)


if __name__ == "__main__":
    n = {"calorie": 300, "protein": 26, "sodium": 605}
    assert score_item("protein", n, None, {})[0] == 26 / 300 * 100
    assert score_item("protein", {"calorie": 300}, None, {}) is None  # 결측 -> 제외
    assert score_item("low_sodium", n, None, {"max_sodium": 500}) is None  # 상한 초과
    assert score_item("diet", n, None, {}) is None  # diet_score 없음
    assert score_item("diet", n, 72, {})[1].endswith("72/100")
    assert score_item("protein", {"calorie": 3, "protein": 1}, None, {}) is None  # 100kcal 미만 제외
    assert is_drink("에스프레소 음료", "아메리카노") and not is_drink("샌드위치", "로스트 치킨")
    # "티" 한 글자 부분일치 오탐 (앞뒤가 한글이면 차가 아니다)
    assert is_drink("티(티바나)", "얼 그레이 티") and is_drink("티", "Earl Grey 얼 그레이")
    assert not is_drink("피자", "그릴드 패티 치즈 버거 씬 L")
    assert not is_drink("사이드", "베이컨 까르보나라 스파게티")
    assert not is_drink("푸드", "떠먹는 티라미수")
    assert not is_drink("아이스크림", "Green Tea 그린티")
    assert score_item("diet", {"calorie": 5}, 100, {}, drink=True)[0] == 100  # 음료는 100kcal 미만도 OK
    assert score_item("protein", {"calorie": 5, "protein": 1}, None, {}, drink=True) is None
    cake = {"calorie": 400, "sodium": 60, "sugar": 35}  # 저나트륨이지만 당 10%E 초과 -> 제외
    assert score_item("low_sodium", cake, None, {}) is None
    assert score_item("low_sodium", {"calorie": 400, "sodium": 60, "sugar": 8}, None, {})[0] == -60
    assert score_item("low_sodium", {"calorie": 400, "sodium": 60}, None, {}) is None  # 당류 결측 -> 모름 -> 제외
    print("ok")
