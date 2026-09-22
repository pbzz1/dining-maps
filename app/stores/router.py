from fastapi import APIRouter, HTTPException

from app.db import get_connection
from app.geo import haversine_m
from app.grading import GRADE_RANK, absolute_grade_for, brand_relative_grades
from app.menu_category import GROUPS, category_group, is_drink
from app.recommend.goals import GOALS, score_item
from app.stores.schemas import BrandRecoOut, StoreOut

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


@router.get("/brand-reco", response_model=list[BrandRecoOut])
def brand_reco(goal: str = "diet", category: str | None = None):
    """선택한 목표·음식 종류 기준으로 브랜드마다 가장 맞는 메뉴 한 건.

    지도 화면이 /api/stores 와 따로 호출한다. 목표만 바꿀 때 반경 안 매장을 다시
    받지 않아도 되고(응답이 브랜드 수만큼이라 작다), 추천 근거가 "브랜드 평균 등급"
    하나에 고정돼 어디서 들어와도 같은 매장만 뜨던 문제도 여기서 풀린다.

    category 는 menu_category.GROUPS 중 하나. 걸면 그 종류 메뉴가 있는 브랜드만 남아
    지도 추천 목록 자체가 바뀐다 (예: '샐러드·샌드위치'면 커피 브랜드가 빠진다).
    """
    if goal not in GOALS:
        raise HTTPException(status_code=400, detail=f"goal must be one of {list(GOALS)}")
    if category is not None and category not in GROUPS:
        raise HTTPException(status_code=400, detail=f"category must be one of {list(GROUPS)}")

    conn = get_connection()
    rows = conn.execute(
        """SELECT mi.id, mi.name, mi.category, mi.restaurant_id,
                  ds.score AS diet_score,
                  json_object_agg(nf.nutrient_name, nf.value) AS nutrients
           FROM menu_item mi
           JOIN nutrition_fact nf ON nf.menu_item_id = mi.id
           LEFT JOIN diet_score ds ON ds.menu_item_id = mi.id
           GROUP BY mi.id, ds.score"""
    ).fetchall()
    conn.close()

    best: dict[int, tuple[float, BrandRecoOut]] = {}
    for row in rows:
        group = category_group(row["category"], row["name"])
        if category is not None and group != category:
            continue
        drink = is_drink(row["category"], row["name"])
        # 음료를 고르지 않았으면 음료는 대표 메뉴가 될 수 없다. 지도는 "지금 뭘 먹을까"의
        # 화면인데, diet 기준으로는 10kcal 아메리카노가 어느 밥집 메뉴보다도 높은 점수라
        # 그대로 두면 커피 브랜드가 추천 1위를 독차지한다.
        if drink and category != "음료":
            continue
        hit = score_item(goal, row["nutrients"], row["diet_score"], {}, drink=drink)
        if hit is None:
            continue
        score, reason = hit
        prev = best.get(row["restaurant_id"])
        if prev is not None and prev[0] >= score:
            continue
        best[row["restaurant_id"]] = (
            score,
            BrandRecoOut(
                restaurant_id=row["restaurant_id"],
                menu_item_id=row["id"],
                menu_name=row["name"],
                category_group=group,
                reason=reason,
                score=round(score, 2),
                rank=0.0,  # 아래에서 브랜드끼리 줄 세운 뒤 채운다
            ),
        )

    # goal 마다 점수 단위가 달라(0~100 / g per 100kcal / -mg) 그대로는 거리와 섞을 수
    # 없다. 응답 안에서의 상대 순위 0~1 로 바꿔 지도 정렬이 쓰게 한다.
    out = [r for _, r in sorted(best.values(), key=lambda t: t[0], reverse=True)]
    last = len(out) - 1
    for i, reco in enumerate(out):
        reco.rank = 1.0 if last == 0 else round((last - i) / last, 4)
    return out
