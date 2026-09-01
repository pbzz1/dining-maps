from pydantic import BaseModel


class NewMenuOut(BaseModel):
    id: int
    name: str
    base_name: str  # 사이즈·세트 접미사를 뗀 이름. 프론트가 옵션 행들을 한 줄로 묶는 키
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
    image_url: str | None  # 브랜드 공식 CDN. 크롤 자동수집 아님 -- 시드로만 채워짐
    youtube_video_id: str | None  # 리뷰 검색 1위 영상 (fetch_youtube_reviews.py 캐시)
    # 같은 브랜드·같은 카테고리 안에서의 백분위 (0=최저, 100=최고).
    # 칼로리는 낮을수록, 단백질은 높을수록 좋은 편.
    calorie_brand_pct: float | None
    protein_brand_pct: float | None
    # LLM 리뷰 (new_menu_review). 배치가 아직 안 돌았으면 None -- 프론트는 영양정보만 보여준다.
    diet_verdict: str | None
    diet_comment: str | None
    taste_note: str | None
