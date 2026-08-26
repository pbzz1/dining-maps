from pydantic import BaseModel


class NewMenuOut(BaseModel):
    id: int
    name: str
    restaurant_id: int
    restaurant_name: str
    category_group: str | None
    event_date: str  # ISO date -- 정렬·표시 기준일 = COALESCE(released_at, first_seen_at)
    released_at: str | None  # 보도자료로 확인된 실제 출시일 (seed_released_at.py)
    first_seen_at: str | None  # 크롤 diff가 처음 발견한 날 (백필 전용 메뉴는 None)
    calorie: float | None
    protein: float | None
    sugar: float | None
    saturated_fat: float | None
    sodium: float | None
    weight_g: float | None
    nutrition_basis: str | None
    diet_score: float | None
    absolute_grade: str | None
    # LLM 리뷰 (new_menu_review). 배치가 아직 안 돌았으면 None -- 프론트는 영양정보만 보여준다.
    diet_verdict: str | None
    diet_comment: str | None
    taste_note: str | None
