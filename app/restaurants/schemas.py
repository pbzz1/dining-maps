from pydantic import BaseModel


class RestaurantOut(BaseModel):
    id: int
    name: str
    # Brand grade inlined so the list page needs one request, not one per brand.
    absolute_grade: str | None = None
    relative_grade: str | None = None
    good_menu_ratio: float | None = None


class NutritionFactOut(BaseModel):
    nutrient_name: str  # calorie / protein / carb / fat / sugar / saturated_fat / sodium / caffeine
    value: float
    unit: str  # kcal / g / mg


class MenuItemOut(BaseModel):
    id: int
    name: str
    category: str | None
    price_krw: int | None
    weight_g: float | None
    allergy_info: str | None
    origin_info: str | None
    data_source: str | None
    nutrition: list[NutritionFactOut]
    diet_score: float | None  # 0-100, see docs/diet_score.md; null if not scored (e.g. <100kcal item)
    absolute_grade: str | None  # A/B/C/D from fixed WHO/논문 cutoffs -- doesn't move with the catalog
    relative_grade: str | None  # A/B/C/D from percentile rank among current catalog -- B is the largest band
    percentile: float | None  # 0-100, this item's percentile rank of diet_score (within the same basis)
    grade_basis: str | None = None  # 'meal' (per-100kcal, protein counts) / 'drink' (per-serving, no protein/sodium)
    # `nutrition` 이 무엇을 담고 있는지: per_serving(기본) / per_total(용기·한 판 전체) / per_100g.
    nutrition_basis: str | None = None
    # per_total 로 적힌 병 음료만 채워진다. 위 `nutrition` 은 용기 전체 값 그대로 두고,
    # 1회분(200ml) 환산값을 따로 내려서 화면이 둘 다 보여줄 수 있게 한다.
    serving_ml: float | None = None
    nutrition_per_serving: list[NutritionFactOut] | None = None


class NutrientAverageOut(BaseModel):
    nutrient_name: str
    unit: str
    avg_value: float
    item_count: int  # how many menu items had this nutrient reported


class RestaurantStatsOut(BaseModel):
    restaurant_id: int
    restaurant_name: str
    menu_item_count: int
    averages: list[NutrientAverageOut]


class RestaurantDietGradeOut(BaseModel):
    restaurant_id: int
    restaurant_name: str
    scored_item_count: int  # menu items with a diet_score (excludes <100kcal items)
    avg_score: float | None
    absolute_grade: str | None  # from avg_score via fixed cutoffs
    relative_grade: str | None  # from avg percentile via the same bands compute_diet_score.py uses
    good_menu_count: int  # items with absolute_grade A or B (WHO-standard "good")
    good_menu_ratio: float | None  # good_menu_count / scored_item_count

