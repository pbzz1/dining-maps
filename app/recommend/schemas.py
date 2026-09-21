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
    saturated_fat: float | None
    goal_score: float  # goal 별 정렬 키. goal 이 다르면 서로 비교 불가.
    reason: str  # "왜 추천했는지" -- 이게 없으면 개인화가 아니라 그냥 정렬로 보인다.
    nearest_store: NearestStoreOut | None = None  # lat/lng 를 줬고 반경 안에 매장이 있을 때만


class GoalOut(BaseModel):
    key: str
    label: str


class PersonalRecoOut(BaseModel):
    """로그인 사용자용 "오늘 당신에겐" 카드. items[].reason 은 LLM이 쓴 개인화 문장이다."""

    # llm: 개인화 성공. rule: 키 없음/호출 실패/거절 -- 룰 상위 3개로 대체했다는 뜻이고,
    # 프론트가 "AI 추천" 배지를 뗄지 결정한다. 화면이 비는 일은 어느 쪽이든 없다.
    source: str
    goal: str
    comment: str | None = None  # 오늘의 한 줄 조언. rule 이면 None.
    items: list[RecommendedMenuOut]
