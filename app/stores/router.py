from fastapi import APIRouter, HTTPException

from app.db import get_connection
from app.geo import haversine_m
from app.grading import GRADE_RANK, absolute_grade_for, brand_relative_grades
from app.stores.schemas import StoreOut

router = APIRouter(prefix="/api/stores", tags=["stores"])

@router.get("", response_model=list[StoreOut])
def list_stores(
    lat: float | None = None,
    lng: float | None = None,
    radius_m: int | None = None,
    grade_type: str = "relative",  # "absolute" or "relative" -- which grade min_grade filters on
    min_grade: str | None = None,  # "A"/"B"/"C"/"D" -- keep stores at or better than this grade
):
    """Store locations with each brand's diet grade attached, optionally
    filtered by distance and/or grade. Populated by scripts/pipeline/fetch_store_locations.py
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

    # LLM 배치 추천 (scripts/llm/generate_menu_reco.py) -- 없는 브랜드는 그냥 None
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
