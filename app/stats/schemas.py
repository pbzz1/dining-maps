"""db/schema.sql 마지막 절의 mart 머티리얼라이즈드 뷰와 1:1."""
from pydantic import BaseModel


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
