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
