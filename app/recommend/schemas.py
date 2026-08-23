from pydantic import BaseModel


class NearestStoreOut(BaseModel):
    id: int
    branch_name: str | None
    address: str | None
    lat: float
    lng: float
    distance_m: float


class RecommendedMenuOut(BaseModel):
    menu_item_id: int
    name: str
    category: str | None
    restaurant_id: int
    restaurant_name: str
    calorie: float | None
    protein: float | None
    sodium: float | None
    sugar: float | None
    goal_score: float  # goal 별 정렬 키. goal 이 다르면 서로 비교 불가.
    reason: str  # "왜 추천했는지" -- 이게 없으면 개인화가 아니라 그냥 정렬로 보인다.
    nearest_store: NearestStoreOut | None = None  # lat/lng 를 줬고 반경 안에 매장이 있을 때만


class GoalOut(BaseModel):
    key: str
    label: str
