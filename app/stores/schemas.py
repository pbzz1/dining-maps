from pydantic import BaseModel


class StoreOut(BaseModel):
    id: int
    restaurant_id: int
    restaurant_name: str
    branch_name: str
    address: str | None
    lat: float
    lng: float
    distance_m: float | None  # only set when the request included lat/lng
    avg_score: float | None  # brand-level average, same for every store of that restaurant
    absolute_grade: str | None
    relative_grade: str | None
    good_menu_ratio: float | None
    reco_menu: str | None = None  # LLM이 뽑은 브랜드 대표 다이어트 추천 메뉴 (brand_menu_reco)
    reco_reason: str | None = None  # 한 문장 추천 이유



class BrandRecoOut(BaseModel):
    """브랜드 한 곳에서, 선택한 목표(goal)·음식 종류(category)에 가장 맞는 메뉴 한 건.

    LLM 배치 추천(brand_menu_reco)과 달리 선택에 따라 매번 다시 계산된다 --
    지도 추천이 언제 들어와도 똑같은 매장만 내놓던 원인이 '브랜드당 고정 1메뉴'였다.
    """

    restaurant_id: int
    menu_item_id: int
    menu_name: str
    category_group: str
    reason: str
    score: float  # goal 별 원점수. goal 이 다르면 서로 비교 불가.
    rank: float  # 0~1, 같은 응답 안에서의 상대 순위(1이 최고). 지도 정렬은 이걸 쓴다.
