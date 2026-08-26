import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.db import get_connection
from app.geo import haversine_m
from app.menu_category import is_drink
from app.recommend.goals import DRINK_SERVING_ML, MIN_CALORIE, serving_ratio
from app.recommend.router import router as recommend_router
from app.schemas import (
    BrandNutritionOut,
    DataQualityOut,
    MenuItemOut,
    MenuRankOut,
    NutrientTrendOut,
    NutrientAverageOut,
    NutritionFactOut,
    RestaurantDietGradeOut,
    RestaurantOut,
    RestaurantStatsOut,
    StoreOut,
)

def absolute_grade_for(score: float) -> str:
    """Fixed WHO/논문-derived cutoffs -- see docs/diet_score.md."""
    if score >= 80:
        return "A"
    if score >= 60:
        return "B"
    if score >= 40:
        return "C"
    return "D"


# Brand-level relative grade: rank every scored brand by avg menu score and
# cut the ranking into even quarters -> A/B/C/D. "A" literally means "top 25%
# of brands in the DB right now", so it moves as brands are added.
BRAND_BANDS = ((0.25, "A"), (0.5, "B"), (0.75, "C"), (1.0, "D"))


def brand_relative_grades(conn) -> dict[int, str]:
    """restaurant_id -> A/B/C/D by rank of avg diet score among all scored brands."""
    rows = conn.execute(
        """SELECT mi.restaurant_id, AVG(ds.score) AS avg_score
           FROM diet_score ds JOIN menu_item mi ON mi.id = ds.menu_item_id
           GROUP BY mi.restaurant_id ORDER BY avg_score DESC, mi.restaurant_id"""
    ).fetchall()
    n = len(rows)
    return {r["restaurant_id"]: next(g for cut, g in BRAND_BANDS if (i + 1) / n <= cut + 1e-9) for i, r in enumerate(rows)}

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
app.include_router(recommend_router)


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
    rel = brand_relative_grades(conn)
    conn.close()
    return [
        RestaurantOut(
            id=r["id"],
            name=r["name"],
            absolute_grade=absolute_grade_for(r["avg_score"]) if r["avg_score"] is not None else None,
            relative_grade=rel.get(r["id"]),
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
                  mi.origin_info, mi.data_source, mi.nutrition_basis, ds.score AS diet_score,
                  ds.absolute_grade, ds.relative_grade, ds.percentile, ds.basis
           FROM menu_item mi
           LEFT JOIN diet_score ds ON ds.menu_item_id = mi.id
           WHERE mi.restaurant_id = %s ORDER BY mi.name""",
        (restaurant_id,),
    ).fetchall()

    # 영양정보는 한 번에 가져와 메뉴별로 묶는다. 메뉴당 1쿼리(N+1)로 하면
    # Lambda(시드니)→Neon(싱가포르) 왕복 ~90ms × 수백 건이라 30초 타임아웃에 걸렸다.
    facts_by_item: dict[int, list] = {}
    for f in conn.execute(
        """SELECT nf.menu_item_id, nf.nutrient_name, nf.value, nf.unit
           FROM nutrition_fact nf JOIN menu_item mi ON mi.id = nf.menu_item_id
           WHERE mi.restaurant_id = %s""",
        (restaurant_id,),
    ):
        facts_by_item.setdefault(f["menu_item_id"], []).append(f)

    result = []
    for item in items:
        facts = facts_by_item.get(item["id"], [])
        # 용기 전체 기준으로만 공개된 병 음료(도미노 1.5L 등)는 1회분 환산값을 함께 내린다.
        # 나트륨·mg 단위까지 같은 배율이라 값만 곱하면 되고, 단위는 그대로다.
        ratio = (
            serving_ratio(item["nutrition_basis"], item["weight_g"])
            if is_drink(item["category"], item["name"])
            else None
        )
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
                grade_basis=item["basis"],
                nutrition_basis=item["nutrition_basis"],
                serving_ml=DRINK_SERVING_ML if ratio else None,
                nutrition_per_serving=[
                    NutritionFactOut(
                        nutrient_name=f["nutrient_name"],
                        value=round(f["value"] * ratio, 1),
                        unit=f["unit"],
                    )
                    for f in facts
                ] if ratio else None,
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
    rel = brand_relative_grades(conn)
    conn.close()

    scored_item_count = row["n"]
    avg_score = round(row["avg_score"], 2) if row["avg_score"] is not None else None
    good_menu_count = row["good_count"] or 0

    return RestaurantDietGradeOut(
        restaurant_id=restaurant["id"],
        restaurant_name=restaurant["name"],
        scored_item_count=scored_item_count,
        avg_score=avg_score,
        absolute_grade=absolute_grade_for(avg_score) if avg_score is not None else None,
        relative_grade=rel.get(restaurant_id),
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
    rel = brand_relative_grades(conn)
    grade_by_restaurant = {
        r["restaurant_id"]: {
            "avg_score": round(r["avg_score"], 2),
            "absolute_grade": absolute_grade_for(r["avg_score"]),
            "relative_grade": rel[r["restaurant_id"]],
            "good_menu_ratio": round(r["good_ratio"], 3),
        }
        for r in grade_rows
    }

    # LLM 배치 추천 (scripts/generate_menu_reco.py) -- 없는 브랜드는 그냥 None
    reco_by_restaurant = {
        r["restaurant_id"]: r
        for r in conn.execute(
            """SELECT br.restaurant_id, mi.name AS reco_menu, br.reason AS reco_reason
               FROM brand_menu_reco br JOIN menu_item mi ON mi.id = br.menu_item_id"""
        ).fetchall()
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
        reco = reco_by_restaurant.get(s["restaurant_id"])
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
                reco_menu=reco["reco_menu"] if reco else None,
                reco_reason=reco["reco_reason"] if reco else None,
            )
        )

    if lat is not None and lng is not None:
        result.sort(key=lambda s: s.distance_m)

    return result


# --- 대시보드 메뉴 탐색기 ---
#
# 정렬 화이트리스트: 정렬 키 -> (ORDER BY 식, 그 정렬이 요구하는 NOT NULL 조건,
# 화면에 보여줄 파생값 식, 단위). 사용자 입력을 SQL 에 넣는 자리라 문자열을 그대로
# 이어붙이지 않고 여기 있는 것만 허용한다.
#
# '왜 nutrition_fact 를 매번 피벗하나': 메뉴 2천여 건 x 영양소 5종이라 인덱스가 걸린
# 조인 한 번이면 끝난다. mart 로 뺄 만큼 무겁지 않고, 뺐다면 필터 조합마다 뷰가
# 하나씩 생겼을 것이다.
#
# 비율 정렬(100kcal당·그램당)에는 goals.MIN_CALORIE 하한을 그대로 쓴다. 안 걸면
# 3kcal 짜리 우롱티(단백질 0.8g)가 100kcal당 23g으로 단백질 1위를 한다 -- 브랜드가
# 단백질을 g 단위로 반올림해 공개하기 때문에, 분모가 한 자릿수면 반올림 오차가
# 비율을 통째로 지배한다. goals.score_item 이 같은 이유로 같은 하한을 쓰고 있다.
MENU_SORTS = {
    "calorie_desc":    ("n.calorie DESC",            "n.calorie IS NOT NULL",   None,                          None),
    "calorie_asc":     ("n.calorie ASC",             "n.calorie IS NOT NULL",   None,                          None),
    "sodium_desc":     ("n.sodium DESC",             "n.sodium IS NOT NULL",    None,                          None),
    "sodium_asc":      ("n.sodium ASC",              "n.sodium IS NOT NULL",    None,                          None),
    "sugar_desc":      ("n.sugar DESC",              "n.sugar IS NOT NULL",     None,                          None),
    "sugar_asc":       ("n.sugar ASC",               "n.sugar IS NOT NULL",     None,                          None),
    "protein_desc":    ("n.protein DESC",            "n.protein IS NOT NULL",   None,                          None),
    # 그램 대비 단백질: 중량을 공개한 메뉴만 줄 세울 수 있다. 중량 없는 메뉴를 0으로
    # 두면 전부 꼴찌로 붙어 순위가 거짓말이 되므로 아예 제외한다.
    # per_100g 브랜드(BHC·교촌)는 제외한다 -- 단백질은 100g당인데 weight_g 는 제품 전체
    # 중량이라, 둘을 나누면 아무 의미 없는 수가 나온다 (해당 40건).
    "protein_per_100g_desc": ("n.protein / mi.weight_g * 100 DESC",
                              f"n.protein IS NOT NULL AND mi.weight_g > 0"
                              f" AND n.calorie >= {MIN_CALORIE}"
                              f" AND mi.nutrition_basis IS DISTINCT FROM 'per_100g'",
                              "n.protein / mi.weight_g * 100", "g/100g"),
    # 100kcal 당 단백질: 중량을 안 밝힌 브랜드도 줄 세울 수 있는 대안.
    "protein_per_100kcal_desc": ("n.protein / n.calorie * 100 DESC",
                                 f"n.protein IS NOT NULL AND n.calorie >= {MIN_CALORIE}",
                                 "n.protein / n.calorie * 100", "g/100kcal"),
    "score_desc":      ("ds.score DESC",             "ds.score IS NOT NULL",    None,                          None),
    "score_asc":       ("ds.score ASC",              "ds.score IS NOT NULL",    None,                          None),
}


@app.get("/api/menus", response_model=list[MenuRankOut])
def list_menus(
    sort: str = "calorie_desc",
    category: str | None = None,
    restaurant_id: int | None = None,
    limit: int = 30,
):
    if sort not in MENU_SORTS:
        raise HTTPException(status_code=400, detail=f"sort must be one of {sorted(MENU_SORTS)}")
    order_by, not_null, sort_expr, sort_unit = MENU_SORTS[sort]
    limit = max(1, min(limit, 100))

    where = [not_null]
    params: list = []
    if category:
        where.append("mi.category_group = %s")
        params.append(category)
    if restaurant_id is not None:
        where.append("mi.restaurant_id = %s")
        params.append(restaurant_id)

    conn = get_connection()
    rows = conn.execute(
        f"""WITH n AS (
                SELECT menu_item_id,
                       MAX(value) FILTER (WHERE nutrient_name = 'calorie')       AS calorie,
                       MAX(value) FILTER (WHERE nutrient_name = 'protein')       AS protein,
                       MAX(value) FILTER (WHERE nutrient_name = 'sugar')         AS sugar,
                       MAX(value) FILTER (WHERE nutrient_name = 'saturated_fat') AS saturated_fat,
                       MAX(value) FILTER (WHERE nutrient_name = 'sodium')        AS sodium
                FROM nutrition_fact GROUP BY menu_item_id
            )
            SELECT mi.id, mi.name, r.name AS restaurant_name,
                   COALESCE(mi.category_group, '기타') AS category_group,
                   n.calorie, n.protein, n.sugar, n.saturated_fat, n.sodium,
                   mi.weight_g, mi.nutrition_basis, ds.score AS diet_score, ds.absolute_grade,
                   {sort_expr or 'NULL'} AS sort_value
            FROM menu_item mi
            JOIN restaurant r    ON r.id = mi.restaurant_id
            JOIN n               ON n.menu_item_id = mi.id
            LEFT JOIN diet_score ds ON ds.menu_item_id = mi.id
            WHERE {' AND '.join(where)}
            ORDER BY {order_by}, mi.id
            LIMIT %s""",
        (*params, limit),
    ).fetchall()
    conn.close()

    return [
        MenuRankOut(
            id=r["id"],
            name=r["name"],
            restaurant_name=r["restaurant_name"],
            category_group=r["category_group"],
            calorie_kcal=r["calorie"],
            protein_g=r["protein"],
            sugar_g=r["sugar"],
            saturated_fat_g=r["saturated_fat"],
            sodium_mg=r["sodium"],
            weight_g=r["weight_g"],
            nutrition_basis=r["nutrition_basis"],
            diet_score=r["diet_score"],
            absolute_grade=r["absolute_grade"],
            sort_value=round(r["sort_value"], 1) if r["sort_value"] is not None else None,
            sort_unit=sort_unit,
        )
        for r in rows
    ]


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
