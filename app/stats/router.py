"""대시보드 통계: mart 머티리얼라이즈드 뷰를 그대로 읽는다. 집계는 파이프라인이
scripts/pipeline/refresh_marts.py 로 미리 해둔다 -- db/schema.sql 마지막 절 참고."""
from fastapi import APIRouter

from app.db import get_connection
from app.stats.schemas import BrandNutritionOut, DataQualityOut, NutrientTrendOut

router = APIRouter(prefix="/api/stats", tags=["stats"])

@router.get("/brands", response_model=list[BrandNutritionOut])
def stats_brands():
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM mart_brand_nutrition ORDER BY avg_score DESC NULLS LAST"
    ).fetchall()
    conn.close()
    return [BrandNutritionOut(**r) for r in rows]


@router.get("/trend", response_model=list[NutrientTrendOut])
def stats_trend():
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM mart_nutrient_trend ORDER BY started_at, restaurant_name, nutrient_name"
    ).fetchall()
    conn.close()
    return [NutrientTrendOut(**{**r, "started_at": r["started_at"].isoformat()}) for r in rows]


@router.get("/quality", response_model=list[DataQualityOut])
def stats_quality():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM mart_data_quality ORDER BY run_id").fetchall()
    conn.close()
    return [DataQualityOut(**{**r, "started_at": r["started_at"].isoformat()}) for r in rows]
