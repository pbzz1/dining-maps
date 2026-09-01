from fastapi import APIRouter, HTTPException

from app.db import get_connection
from app.grading import absolute_grade_for, brand_relative_grades
from app.menu_category import is_drink
from app.recommend.goals import DRINK_SERVING_ML, serving_ratio
from app.restaurants.schemas import (
    MenuItemOut,
    NutrientAverageOut,
    NutritionFactOut,
    RestaurantDietGradeOut,
    RestaurantOut,
    RestaurantStatsOut,
)

router = APIRouter(prefix="/api/restaurants", tags=["restaurants"])

def get_restaurant_or_404(conn, restaurant_id: int):
    row = conn.execute(
        "SELECT id, name FROM restaurant WHERE id = %s", (restaurant_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    return row


@router.get("", response_model=list[RestaurantOut])
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


@router.get("/{restaurant_id}/menu", response_model=list[MenuItemOut])
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


@router.get("/{restaurant_id}/stats", response_model=RestaurantStatsOut)
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


@router.get("/{restaurant_id}/diet-grade", response_model=RestaurantDietGradeOut)
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
