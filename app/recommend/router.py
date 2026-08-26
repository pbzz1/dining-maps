from fastapi import APIRouter, HTTPException

from app.db import get_connection
from app.geo import haversine_m
from app.recommend.goals import GOALS, is_drink, score_item
from app.recommend.schemas import GoalOut, NearestStoreOut, RecommendedMenuOut

router = APIRouter(prefix="/api/recommend", tags=["recommend"])


@router.get("/goals", response_model=list[GoalOut])
def list_goals():
    return [GoalOut(key=k, label=v["label"]) for k, v in GOALS.items()]


@router.get("/menus", response_model=list[RecommendedMenuOut])
def recommend_menus(
    goal: str = "diet",
    max_calorie: float | None = None,
    max_sodium: float | None = None,
    max_sugar: float | None = None,
    exclude_drinks: bool = False,
    lat: float | None = None,
    lng: float | None = None,
    radius_m: int = 3000,
    limit: int = 20,
):
    """goal 기준 상위 메뉴. lat/lng 를 주면 각 메뉴 브랜드의 반경 내 가장 가까운 매장을 붙인다.
    매장 데이터는 브랜드 단위 메뉴와 동일하다고 가정한다 (지점별 메뉴 차이는 무시)."""
    if goal not in GOALS:
        raise HTTPException(status_code=400, detail=f"goal must be one of {list(GOALS)}")
    limits = {"max_calorie": max_calorie, "max_sodium": max_sodium, "max_sugar": max_sugar}

    conn = get_connection()
    rows = conn.execute(
        """SELECT mi.id, mi.name, mi.category, mi.restaurant_id, r.name AS restaurant_name,
                  ds.score AS diet_score,
                  json_object_agg(nf.nutrient_name, nf.value) AS nutrients
           FROM menu_item mi
           JOIN restaurant r ON r.id = mi.restaurant_id
           JOIN nutrition_fact nf ON nf.menu_item_id = mi.id
           LEFT JOIN diet_score ds ON ds.menu_item_id = mi.id
           GROUP BY mi.id, r.name, ds.score"""
    ).fetchall()

    scored = []
    for row in rows:
        drink = is_drink(row["category"], row["name"])
        if exclude_drinks and drink:
            continue
        hit = score_item(goal, row["nutrients"], row["diet_score"], limits, drink=drink)
        if hit:
            scored.append((hit[0], hit[1], row))
    scored.sort(key=lambda t: t[0], reverse=True)
    top = scored[:limit]

    # 근처 매장: 상위 메뉴의 브랜드만 조회해서 브랜드별 최단 거리 1곳.
    nearest = {}
    if lat is not None and lng is not None and top:
        ids = list({t[2]["restaurant_id"] for t in top})
        stores = conn.execute(
            "SELECT id, restaurant_id, branch_name, address, lat, lng FROM store WHERE restaurant_id = ANY(%s)",
            (ids,),
        ).fetchall()
        for s in stores:
            d = haversine_m(lat, lng, s["lat"], s["lng"])
            if d <= radius_m and (s["restaurant_id"] not in nearest or d < nearest[s["restaurant_id"]][0]):
                nearest[s["restaurant_id"]] = (d, s)
    conn.close()

    out = []
    for score, reason, row in top:
        n = row["nutrients"]
        ns = nearest.get(row["restaurant_id"])
        out.append(
            RecommendedMenuOut(
                menu_item_id=row["id"],
                name=row["name"],
                category=row["category"],
                restaurant_id=row["restaurant_id"],
                restaurant_name=row["restaurant_name"],
                calorie=n.get("calorie"),
                protein=n.get("protein"),
                sodium=n.get("sodium"),
                sugar=n.get("sugar"),
                saturated_fat=n.get("saturated_fat"),
                goal_score=round(score, 2),
                reason=reason,
                nearest_store=NearestStoreOut(
                    id=ns[1]["id"],
                    branch_name=ns[1]["branch_name"],
                    address=ns[1]["address"],
                    lat=ns[1]["lat"],
                    lng=ns[1]["lng"],
                    distance_m=round(ns[0], 1),
                )
                if ns
                else None,
            )
        )
    return out
