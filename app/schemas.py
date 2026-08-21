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
    percentile: float | None  # 0-100, this item's percentile rank of diet_score


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


# --- 대시보드 mart (app/main.py /api/stats/*, db/schema.sql의 MV와 1:1) ---

class BrandNutritionOut(BaseModel):
    restaurant_id: int
    restaurant_name: str
    menu_count: int
    store_count: int
    scored_count: int
    avg_score: float | None
    grade_a: int
    grade_b: int
    grade_c: int
    grade_d: int
    avg_calorie_kcal: float | None
    avg_sodium_mg: float | None
    avg_sugar_g: float | None
    avg_protein_g: float | None


class NutrientTrendOut(BaseModel):
    run_id: int
    started_at: str
    restaurant_name: str
    nutrient_name: str
    unit: str
    avg_value: float
    item_count: int


class DataQualityOut(BaseModel):
    run_id: int
    started_at: str
    source: str
    status: str
    checks_total: int
    checks_pass: int
    checks_warn: int
    checks_fail: int
    real_changes: int
    suspected_parser_bugs: int
