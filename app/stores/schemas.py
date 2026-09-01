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

