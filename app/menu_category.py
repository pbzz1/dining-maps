"""브랜드 제각각인 menu_item.category(130여 종)를 사용자가 필터로 쓸 수 있는
소수의 그룹으로 정규화한다.

원본 category 를 그대로 못 쓰는 이유:
  - 버거킹: category 칸에 메뉴 이름이 그대로 들어있다 (85종, 대부분 1건)
  - 맥도날드: 전 메뉴 category 가 비어 있다
  - 나머지: '신음료' '에스프레소' '버거메뉴' '푸드' 처럼 브랜드마다 다른 말

그래서 category + 이름을 합친 문자열에 키워드를 순서대로 맞춰본다. 순서가
분류 결과를 결정하므로 GROUP_KEYWORDS 는 '더 구체적인 것 먼저'로 정렬돼 있다.

음료 판정만 별도로 앞에 두는 이유: is_drink 는 이미 diet_score 의 채점 기준
(basis: meal/drink)을 가르는 데 쓰이고 있어서, 여기서 순서를 바꾸면 이미 매겨진
점수가 조용히 흔들린다. 음료를 맨 앞에 고정해 is_drink 의 판정을 그대로 보존한다.
"""
import re

# ---- 음료 (app/recommend/goals.py 에서 옮겨옴, 판정 로직 변경 없음) ----
DRINK_KEYWORDS = ("음료", "커피", "에스프레소", "라떼", "브루", "프라푸치노", "블렌디드", "주스",
                  "스무디", "스파클링", "피지오", "아이스샷", "리프레셔", "쉐이크", "아메리카노", "초코",
                  "드링크", "소다", "빙수", "할리치노",
                  # 컴포즈커피(19)·폴바셋(38)의 음료 카테고리명. 다른 브랜드 데이터에는
                  # 이 문자열이 없음을 확인하고 추가 (2026-09-01 DB 전수 검사).
                  "베버리지")

# "티"(차)만 한 글자라 부분일치로 쓰면 패**티**·스파게**티**·로**티**세리·**티**라미수·그린**티**가
# 전부 음료로 잡힌다 (실제로 도미노 피자 23개가 음료 기준으로 채점되고 있었다). 앞뒤가 한글이
# 아닐 때만 "티"로 인정한다 -- 스타벅스 "티(티바나)"·커피빈 "티" 카테고리와 "... 블랙 티" 같은
# 이름은 그대로 잡히고, 위 오탐 36건은 전부 빠진다.
DRINK_TEA_RE = re.compile(r"(?<![가-힣])티(?![가-힣])")

# category 는 보지 않고 이름에만 맞춰보는 키워드. 브랜드가 category 를 음료로 달아주지
# 않은 음료를 줍기 위한 것인데, category 까지 보면 안 되는 이유가 둘 있다:
#   - 버거킹 세트의 category 는 "데리야킹 크리스퍼 + 프렌치프라이(R) + 코카콜라(R)"
#     처럼 구성품 나열이라, 세트가 통째로 음료가 된다.
#   - BHC "후라이드(반)+뿌링치즈볼 +콜라245ml" 같은 콤보도 마찬가지다.
# 그래서 '콜라'·'사이다' 류는 아예 넣지 않는다 -- 실제 탄산음료는 전부 brand category 가
# '음료'/'드링크 메뉴'라 위 DRINK_KEYWORDS 로 이미 잡히고, 이름 매칭을 더하면 콤보와
# 배스킨라빈스 '트로피컬 콜라다'만 잘못 걸린다 (data 전수 확인).
NAME_ONLY_DRINK_KEYWORDS = ("플로트", "미닛메이드")

# 위에서부터 먼저 맞는 그룹이 이긴다. 음료는 별도 처리라 여기 없다.
#
# 순서를 이렇게 둔 이유 (전부 data/*.csv 2,221건에 돌려보고 정한 것):
#   버거 > 치킨      '상하이 스파이시 치킨버거'는 치킨이 아니라 버거
#   피자 > 버거      도미노 '그릴드 패티 치즈 버거 씬 L'은 피자
#   샌드위치 > 치킨  서브웨이 '로스트 치킨'은 샌드위치
#   사이드 > 디저트  롯데리아가 포테이토·치즈스틱·코울슬로를 '디저트 메뉴'로 묶어놨다
GROUP_KEYWORDS = (
    ("피자", ("피자", "핏자")),
    # '리아'(롯데리아 버거 라인)와 '휠레'는 뺐다 -- 브랜드 이름이 들어간 '롯데리아케첩'과
    # '치킨휠레'까지 버거로 잡았고, 둘 다 원래 category('버거메뉴'/'치킨메뉴')로 정확히 걸린다.
    ("버거", ("버거", "와퍼", "빅맥", "맥스파이시", "맥치킨", "맥크리스피", "불고기",
              "핫크리스피", "통새우", "오리지널스", "맥시멈", "쿼터파운더")),
    ("샐러드·샌드위치", ("샐러드", "샌드위치", "샌드", "랩", "포케", "서브", "토스트", "베이글",
                        "부리또", "리또", "크루아상위치", "파니니", "포카치아", "크로크")),
    ("치킨", ("치킨", "윙", "닭", "순살", "텐더", "크리스퍼", "너겟", "치큰", "콤보",
              "슈프림", "골드킹", "뿌링클", "맛초킹", "커넬", "콜팝", "지파이")),
    ("사이드", ("사이드", "감자", "후라이", "프라이", "포테이토", "스틱", "치즈볼", "코울슬로",
                "소스", "시즈닝", "해쉬", "핫도그", "떡", "면", "파스타", "스파게티", "밥",
                "돈까스", "오징어", "샐러디", "토핑")),
    ("디저트", ("아이스크림", "케이크", "도넛", "쿠키", "베이커리", "디저트", "마카롱", "와플",
                "파이", "머핀", "스콘", "티라미수", "츄러스", "선데", "블리자드", "빵", "브레드",
                "크로플", "롤케", "타르트", "젤라", "요거트", "푸딩", "소프트", "맥플러리",
                "핫케익", "휘낭시에", "마들렌", "카스테라", "카스텔라", "크레이프", "뚱카롱",
                "몽블랑", "크루아상")),
)

# 필터 UI 가 그리는 순서. "전체"는 프런트에서 붙인다.
GROUPS = ("버거", "치킨", "피자", "샐러드·샌드위치", "음료", "디저트", "사이드", "기타")


def is_drink(category: str | None, name: str) -> bool:
    text = f"{category or ''} {name}"
    return (
        any(k in text for k in DRINK_KEYWORDS)
        or bool(DRINK_TEA_RE.search(text))
        or any(k in name for k in NAME_ONLY_DRINK_KEYWORDS)
    )


def category_group(category: str | None, name: str) -> str:
    """menu_item 한 건을 GROUPS 중 하나로 분류한다. 항상 값을 돌려준다(최후는 '기타')."""
    text = f"{category or ''} {name}"
    if is_drink(category, name):
        return "음료"
    for group, keywords in GROUP_KEYWORDS:
        if any(k in text for k in keywords):
            return group
    return "기타"


if __name__ == "__main__":
    # 음료 판정은 goals.py 에서 옮겨온 것이라 기존 케이스가 그대로 통과해야 한다.
    assert is_drink("에스프레소 음료", "아메리카노") and not is_drink("샌드위치", "로스트 치킨")
    assert is_drink("티(티바나)", "얼 그레이 티") and is_drink("티", "Earl Grey 얼 그레이")
    assert not is_drink("피자", "그릴드 패티 치즈 버거 씬 L")
    assert not is_drink("사이드", "베이컨 까르보나라 스파게티")
    assert not is_drink("푸드", "떠먹는 티라미수")
    assert not is_drink("아이스크림", "Green Tea 그린티")

    assert category_group("에스프레소 음료", "아메리카노") == "음료"
    assert category_group("버거메뉴", "리아 두툼새우") == "버거"
    assert category_group(None, "상하이 스파이시 치킨버거") == "버거"  # 치킨보다 버거 우선
    assert category_group("치킨", "간장윙박스20PCS") == "치킨"
    assert category_group("피자", "그릴드 패티 치즈 버거 씬 L") == "피자"  # 피자가 버거보다 우선
    assert category_group("샌드위치", "로스트 치킨") == "샐러드·샌드위치"
    assert category_group("아이스크림", "Green Tea 그린티") == "디저트"
    assert category_group("사이드", "베이컨 까르보나라 스파게티") == "사이드"
    assert category_group(None, "") == "기타"
    # 실제 데이터에서 잡았던 오분류들 (data/*.csv 전수 확인)
    assert category_group("디저트 메뉴", "포테이토") == "사이드"        # 롯데리아가 사이드를 디저트로 묶어둠
    assert category_group("디저트 메뉴", "지파이 고소한맛(S)") == "치킨"
    assert category_group("BHC시그니처", "뿌링콜팝") == "치킨"
    # 맥도날드 CSV 는 분류를 menu_category 가 아니라 menu_group 칸에 담고, load_data.py 가
    # 그걸 category 로 넣는다 -- 탄산음료는 category='음료'라 DRINK_KEYWORDS 로 잡힌다.
    assert category_group("음료", "스프라이트® 미디엄") == "음료"
    assert category_group("음료", "코카 콜라® 제로 미디엄") == "음료"
    assert category_group("아이스크림", "Almond Bon Bon 아몬드 봉봉") == "디저트"  # '봉'->치킨 오탐
    assert category_group("디저트", "우베 소프트") == "디저트"
    # 세트 category 가 구성품을 나열해도 음료로 넘어가지 않아야 한다
    assert category_group("펜타치즈와퍼 + 프렌치프라이(R) + 코카콜라(R)", "펜타치즈와퍼 라지세트") == "버거"
    assert category_group("소스& 샐러드", "롯데리아케첩(9g)") != "버거"
    assert category_group("치킨메뉴", "치킨휠레2조각 (소스미포함)") == "치킨"
    # 이름에 음료가 섞인 콤보/세트는 음료가 아니다 (NAME_ONLY 에 '콜라'를 넣지 않는 이유)
    assert category_group("치킨", "후라이드(반)+뿌링치즈볼 +콜라245ml") == "치킨"
    assert category_group("아이스크림", "Tropical Colada 트로피컬 콜라다") == "디저트"
    # 반대로, 브랜드가 category 를 안 달아준 진짜 음료는 이름으로 줍는다
    assert is_drink("킹플로트 메론", "킹플로트 메론")
    assert is_drink("미닛메이드 오렌지", "미닛메이드 오렌지")
    print("ok")
