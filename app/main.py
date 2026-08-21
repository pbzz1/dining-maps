import math
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.db import get_connection
from app.schemas import (
    BrandNutritionOut,
    DataQualityOut,
    MenuItemOut,
    NutrientTrendOut,
    NutrientAverageOut,
    NutritionFactOut,
    RestaurantDietGradeOut,
    RestaurantOut,
    RestaurantStatsOut,
    StoreOut,
)

EARTH_RADIUS_M = 6371000


def haversine_m(lat1, lng1, lat2, lng2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def absolute_grade_for(score: float) -> str:
    """Fixed WHO/논문-derived cutoffs -- see docs/diet_score.md."""
    if score >= 80:
        return "A"
    if score >= 60:
        return "B"
    if score >= 40:
        return "C"
    return "D"


def relative_grade_for(percentile: float) -> str:
    """Percentile-band cutoffs matching scripts/compute_diet_score.py
    (A>=85, B>=35, C>=10, else D) so B is the largest band."""
    if percentile >= 85:
        return "A"
    if percentile >= 35:
        return "B"
    if percentile >= 10:
        return "C"
    return "D"

app = FastAPI(title="Dining Maps API")

# The frontend is a separate Vite/React app on its own origin, so the API has to
# opt into cross-origin requests. Origins are listed explicitly rather than "*"
# -- add the deployed frontend URL via ALLOWED_ORIGINS (comma-separated) when
# deploying. In dev the Vite proxy makes requests same-origin anyway, but a
# direct browser call to :8000 still needs this.
DEFAULT_ALLOWED_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get("ALLOWED_ORIGINS", ",".join(DEFAULT_ALLOWED_ORIGINS)).split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def get_restaurant_or_404(conn, restaurant_id: int):
    row = conn.execute(
        "SELECT id, name FROM restaurant WHERE id = %s", (restaurant_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    return row


@app.get("/api/restaurants", response_model=list[RestaurantOut])
def list_restaurants():
    conn = get_connection()
    rows = conn.execute(
        """SELECT r.id, r.name, g.avg_score, g.avg_percentile, g.good_ratio
           FROM restaurant r
           LEFT JOIN (
               SELECT mi.restaurant_id,
                      AVG(ds.score) AS avg_score,
                      AVG(ds.percentile) AS avg_percentile,
                      SUM(CASE WHEN ds.absolute_grade IN ('A','B') THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS good_ratio
               FROM diet_score ds
               JOIN menu_item mi ON mi.id = ds.menu_item_id
               GROUP BY mi.restaurant_id
           ) g ON g.restaurant_id = r.id
           ORDER BY r.name"""
    ).fetchall()
    conn.close()
    return [
        RestaurantOut(
            id=r["id"],
            name=r["name"],
            absolute_grade=absolute_grade_for(r["avg_score"]) if r["avg_score"] is not None else None,
            relative_grade=relative_grade_for(r["avg_percentile"]) if r["avg_percentile"] is not None else None,
            good_menu_ratio=round(r["good_ratio"], 3) if r["good_ratio"] is not None else None,
        )
        for r in rows
    ]


@app.get("/api/restaurants/{restaurant_id}/menu", response_model=list[MenuItemOut])
def get_restaurant_menu(restaurant_id: int):
    conn = get_connection()
    get_restaurant_or_404(conn, restaurant_id)

    items = conn.execute(
        """SELECT mi.id, mi.name, mi.category, mi.price_krw, mi.weight_g, mi.allergy_info,
                  mi.origin_info, mi.data_source, ds.score AS diet_score,
                  ds.absolute_grade, ds.relative_grade, ds.percentile
           FROM menu_item mi
           LEFT JOIN diet_score ds ON ds.menu_item_id = mi.id
           WHERE mi.restaurant_id = %s ORDER BY mi.name""",
        (restaurant_id,),
    ).fetchall()

    result = []
    for item in items:
        facts = conn.execute(
            "SELECT nutrient_name, value, unit FROM nutrition_fact WHERE menu_item_id = %s",
            (item["id"],),
        ).fetchall()
        result.append(
            MenuItemOut(
                id=item["id"],
                name=item["name"],
                category=item["category"],
                price_krw=item["price_krw"],
                weight_g=item["weight_g"],
                allergy_info=item["allergy_info"],
                origin_info=item["origin_info"],
                data_source=item["data_source"],
                nutrition=[
                    NutritionFactOut(nutrient_name=f["nutrient_name"], value=f["value"], unit=f["unit"])
                    for f in facts
                ],
                diet_score=item["diet_score"],
                absolute_grade=item["absolute_grade"],
                relative_grade=item["relative_grade"],
                percentile=item["percentile"],
            )
        )
    conn.close()
    return result


@app.get("/api/restaurants/{restaurant_id}/stats", response_model=RestaurantStatsOut)
def get_restaurant_stats(restaurant_id: int):
    conn = get_connection()
    restaurant = get_restaurant_or_404(conn, restaurant_id)

    menu_item_count = conn.execute(
        "SELECT COUNT(*) AS n FROM menu_item WHERE restaurant_id = %s", (restaurant_id,)
    ).fetchone()["n"]

    rows = conn.execute(
        """SELECT nf.nutrient_name, nf.unit, AVG(nf.value) AS avg_value, COUNT(*) AS item_count
           FROM nutrition_fact nf
           JOIN menu_item mi ON mi.id = nf.menu_item_id
           WHERE mi.restaurant_id = %s
           GROUP BY nf.nutrient_name, nf.unit
           ORDER BY nf.nutrient_name""",
        (restaurant_id,),
    ).fetchall()
    conn.close()

    return RestaurantStatsOut(
        restaurant_id=restaurant["id"],
        restaurant_name=restaurant["name"],
        menu_item_count=menu_item_count,
        averages=[
            NutrientAverageOut(
                nutrient_name=r["nutrient_name"],
                unit=r["unit"],
                avg_value=round(r["avg_value"], 2),
                item_count=r["item_count"],
            )
            for r in rows
        ],
    )


@app.get("/api/restaurants/{restaurant_id}/diet-grade", response_model=RestaurantDietGradeOut)
def get_restaurant_diet_grade(restaurant_id: int):
    """Brand-level diet-friendliness grade. See docs/diet_score.md for the formula
    and why absolute_grade and relative_grade are reported side by side rather
    than picking just one."""
    conn = get_connection()
    restaurant = get_restaurant_or_404(conn, restaurant_id)

    row = conn.execute(
        """SELECT COUNT(*) AS n, AVG(ds.score) AS avg_score, AVG(ds.percentile) AS avg_percentile,
                  SUM(CASE WHEN ds.absolute_grade IN ('A', 'B') THEN 1 ELSE 0 END) AS good_count
           FROM diet_score ds
           JOIN menu_item mi ON mi.id = ds.menu_item_id
           WHERE mi.restaurant_id = %s""",
        (restaurant_id,),
    ).fetchone()
    conn.close()

    scored_item_count = row["n"]
    avg_score = round(row["avg_score"], 2) if row["avg_score"] is not None else None
    avg_percentile = row["avg_percentile"]
    good_menu_count = row["good_count"] or 0

    return RestaurantDietGradeOut(
        restaurant_id=restaurant["id"],
        restaurant_name=restaurant["name"],
        scored_item_count=scored_item_count,
        avg_score=avg_score,
        absolute_grade=absolute_grade_for(avg_score) if avg_score is not None else None,
        relative_grade=relative_grade_for(avg_percentile) if avg_percentile is not None else None,
        good_menu_count=good_menu_count,
        good_menu_ratio=round(good_menu_count / scored_item_count, 3) if scored_item_count else None,
    )


GRADE_RANK = {"A": 0, "B": 1, "C": 2, "D": 3}  # lower is better, for "at least this grade" filtering


@app.get("/api/stores", response_model=list[StoreOut])
def list_stores(
    lat: float | None = None,
    lng: float | None = None,
    radius_m: int | None = None,
    grade_type: str = "relative",  # "absolute" or "relative" -- which grade min_grade filters on
    min_grade: str | None = None,  # "A"/"B"/"C"/"D" -- keep stores at or better than this grade
):
    """Store locations with each brand's diet grade attached, optionally
    filtered by distance and/or grade. Populated by scripts/fetch_store_locations.py
    (empty until the Kakao REST API key is wired in).

    - Pass lat & lng to get distance_m on every result, sorted nearest-first.
      Add radius_m to also drop anything farther than that.
    - Pass min_grade (with optional grade_type) to only keep brands whose
      absolute_grade or relative_grade is at least that good -- see
      docs/diet_score.md for why there are two grade systems.
    """
    if grade_type not in ("absolute", "relative"):
        raise HTTPException(status_code=400, detail="grade_type must be 'absolute' or 'relative'")
    if min_grade is not None and min_grade not in GRADE_RANK:
        raise HTTPException(status_code=400, detail="min_grade must be one of A/B/C/D")

    conn = get_connection()

    grade_rows = conn.execute(
        """SELECT mi.restaurant_id,
                  AVG(ds.score) AS avg_score,
                  AVG(ds.percentile) AS avg_percentile,
                  SUM(CASE WHEN ds.absolute_grade IN ('A','B') THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS good_ratio
           FROM diet_score ds
           JOIN menu_item mi ON mi.id = ds.menu_item_id
           GROUP BY mi.restaurant_id"""
    ).fetchall()
    grade_by_restaurant = {
        r["restaurant_id"]: {
            "avg_score": round(r["avg_score"], 2),
            "absolute_grade": absolute_grade_for(r["avg_score"]),
            "relative_grade": relative_grade_for(r["avg_percentile"]),
            "good_menu_ratio": round(r["good_ratio"], 3),
        }
        for r in grade_rows
    }

    stores = conn.execute(
        """SELECT s.id, s.restaurant_id, r.name AS restaurant_name, s.branch_name, s.address, s.lat, s.lng
           FROM store s
           JOIN restaurant r ON r.id = s.restaurant_id"""
    ).fetchall()
    conn.close()

    result = []
    for s in stores:
        distance_m = None
        if lat is not None and lng is not None:
            distance_m = haversine_m(lat, lng, s["lat"], s["lng"])
            if radius_m is not None and distance_m > radius_m:
                continue

        grades = grade_by_restaurant.get(s["restaurant_id"])
        if min_grade is not None:
            grade_to_check = grades[f"{grade_type}_grade"] if grades else None
            if grade_to_check is None or GRADE_RANK[grade_to_check] > GRADE_RANK[min_grade]:
                continue

        result.append(
            StoreOut(
                id=s["id"],
                restaurant_id=s["restaurant_id"],
                restaurant_name=s["restaurant_name"],
                branch_name=s["branch_name"],
                address=s["address"],
                lat=s["lat"],
                lng=s["lng"],
                distance_m=round(distance_m, 1) if distance_m is not None else None,
                avg_score=grades["avg_score"] if grades else None,
                absolute_grade=grades["absolute_grade"] if grades else None,
                relative_grade=grades["relative_grade"] if grades else None,
                good_menu_ratio=grades["good_menu_ratio"] if grades else None,
            )
        )

    if lat is not None and lng is not None:
        result.sort(key=lambda s: s.distance_m)

    return result


# --- 대시보드: mart 머티리얼라이즈드 뷰를 그대로 읽는다 (집계는 파이프라인이
# scripts/refresh_marts.py 로 미리 해둔다 -- db/schema.sql 마지막 절 참고) ---

@app.get("/api/stats/brands", response_model=list[BrandNutritionOut])
def stats_brands():
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM mart_brand_nutrition ORDER BY avg_score DESC NULLS LAST"
    ).fetchall()
    conn.close()
    return [BrandNutritionOut(**r) for r in rows]


@app.get("/api/stats/trend", response_model=list[NutrientTrendOut])
def stats_trend():
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM mart_nutrient_trend ORDER BY started_at, restaurant_name, nutrient_name"
    ).fetchall()
    conn.close()
    return [NutrientTrendOut(**{**r, "started_at": r["started_at"].isoformat()}) for r in rows]


@app.get("/api/stats/quality", response_model=list[DataQualityOut])
def stats_quality():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM mart_data_quality ORDER BY run_id").fetchall()
    conn.close()
    return [DataQualityOut(**{**r, "started_at": r["started_at"].isoformat()}) for r in rows]


# No StaticFiles mount here on purpose: the frontend is now its own Vite/React
# app (frontend-react/) served separately. Mounting it at "/" also used to
# swallow every unmatched route, which made 404s from the API indistinguishable
# from missing static files.
