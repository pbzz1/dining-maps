from pydantic import BaseModel


class MenuRankOut(BaseModel):
    """메뉴 탐색기(/api/menus) 한 행. 정렬 기준이 무엇이든 같은 필드를 내려서
    프런트가 표 컬럼을 바꿔 끼울 필요가 없게 한다."""
    id: int
    name: str
    restaurant_name: str
    category_group: str
    calorie_kcal: float | None
    protein_g: float | None
    sugar_g: float | None
    saturated_fat_g: float | None
    sodium_mg: float | None
    weight_g: float | None
    # 이 행의 영양정보가 무엇을 기준으로 적힌 값인지. 브랜드마다 달라서(BHC·교촌은
    # 100g, 도미노 병음료는 용기 전체) 절대값 정렬은 이걸 같이 봐야 읽을 수 있다.
    nutrition_basis: str | None = None
    diet_score: float | None
    absolute_grade: str | None
    # 정렬에 쓴 파생값. 화면이 "무엇으로 줄 세웠는지"를 그대로 보여주기 위한 것이라
    # 정렬 기준이 파생값이 아닐 때(칼로리 등)는 null.
    sort_value: float | None = None
    sort_unit: str | None = None

