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
    comment: str | None = None  # 오늘의 한 줄 조언. llm 일 때만.
    items: list[RecommendedMenuOut]
    # 이번 호출에서 새로 기억한 취향(llm 일 때만). 화면이 "이걸 기억해 둘게요"라고 알려 주는 데 쓴다 --
    # AI가 몰래 기억을 쌓지 않는다는 게 사용자에게 보여야 한다.
    memory_added: list[str] = []
    # 이 3개를 보여준 노출 기록 id. 프론트가 저장·빼기·클릭 이벤트에 붙여 보낸다 -- 그래야
    # "보여준 것 중 무엇을 골랐고 무엇을 무시했나"를 학습할 수 있다. 후보가 없으면(rule) None.
    impression_id: int | None = None
    variant: str = "control"  # 효과 측정 비교군. control = 기존 규칙, ml = 학습형
    # 요금제(free / standard / high). 유료인데 source 가 llm 이 아니면 limit_reason 이 이유를 말한다:
    # budget(이번 기간 AI 예산 소진) / daily(오늘 상한) / input(입력이 너무 김). None 이면 호출 실패·캐시 등.
    plan: str = "free"
    limit_reason: str | None = None
    # 이번 이용권의 남은 AI 예산 비율(유료만). 화면이 막대 없이 글자로 보여준다.
    ai_budget_left_pct: int | None = None
