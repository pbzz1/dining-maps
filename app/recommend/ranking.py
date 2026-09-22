"""추천 후보 뽑기: 영양 데이터 조회 -> goal 채점 -> 정렬 -> 근처 매장 붙이기.

/api/recommend/menus(룰 목록)와 /api/recommend/personal(LLM 카드)이 같은 후보에서
출발해야 해서 라우터에서 떼어 냈다. 두 화면이 서로 다른 기준으로 거르면 "목록엔
없는 메뉴를 AI가 추천"하는 모순이 생긴다.
"""
from collections import Counter

from app.geo import haversine_m
from app.recommend.goals import is_drink, score_item
from app.recommend.schemas import NearestStoreOut, RecommendedMenuOut


def fetch_menus(conn):
    """전 메뉴 + 영양성분(피벗 dict) + diet_score. 영양성분은 key-value 행이라 여기서 묶는다."""
    return conn.execute(
        """SELECT mi.id, mi.name, mi.category, mi.restaurant_id, r.name AS restaurant_name,
                  mi.allergy_info, mi.category_group, ds.score AS diet_score,
                  json_object_agg(nf.nutrient_name, nf.value) AS nutrients
           FROM menu_item mi
           JOIN restaurant r ON r.id = mi.restaurant_id
           JOIN nutrition_fact nf ON nf.menu_item_id = mi.id
           LEFT JOIN diet_score ds ON ds.menu_item_id = mi.id
           GROUP BY mi.id, r.name, ds.score"""
    ).fetchall()


def rank(rows, goal, limits, exclude_drinks=False, skip=None):
    """[(score, reason, row)] 점수 내림차순. skip(row)이 True면 채점 전에 뺀다
    (알레르기·숨긴 메뉴 같은 개인 제약용 -- 룰 목록은 None)."""
    scored = []
    for row in rows:
        if skip and skip(row):
            continue
        drink = is_drink(row["category"], row["name"])
        if exclude_drinks and drink:
            continue
        hit = score_item(goal, row["nutrients"], row["diet_score"], limits, drink=drink)
        if hit:
            scored.append((hit[0], hit[1], row))
    scored.sort(key=lambda t: t[0], reverse=True)
    return scored


def diversify(scored, per_brand, limit):
    """점수순을 유지한 채 브랜드당 per_brand개까지만 담아 limit개. 점수 하나로만 자르면
    샐러드·샌드위치 브랜드 두어 곳이 목록을 통째로 차지해 매번 같은 매장만 나온다."""
    counts, picked = Counter(), []
    for t in scored:
        brand = t[2]["restaurant_id"]
        if counts[brand] >= per_brand:
            continue
        counts[brand] += 1
        picked.append(t)
        if len(picked) == limit:
            break
    return picked


def nearest_stores(conn, restaurant_ids, lat, lng, radius_m):
    """{restaurant_id: (거리m, store행)} -- 브랜드별 반경 내 최단 거리 1곳."""
    nearest = {}
    if lat is None or lng is None or not restaurant_ids:
        return nearest
    stores = conn.execute(
        "SELECT id, restaurant_id, branch_name, address, lat, lng FROM store WHERE restaurant_id = ANY(%s)",
        (list(restaurant_ids),),
    ).fetchall()
    for s in stores:
        d = haversine_m(lat, lng, s["lat"], s["lng"])
        if d <= radius_m and (s["restaurant_id"] not in nearest or d < nearest[s["restaurant_id"]][0]):
            nearest[s["restaurant_id"]] = (d, s)
    return nearest


def to_out(score, reason, row, nearest) -> RecommendedMenuOut:
    n = row["nutrients"]
    ns = nearest.get(row["restaurant_id"])
    return RecommendedMenuOut(
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


if __name__ == "__main__":
    # python -m app.recommend.ranking
    rows = [(100 - i, "", {"restaurant_id": 1}) for i in range(10)] + [(50, "", {"restaurant_id": 2})]
    rows.sort(key=lambda t: t[0], reverse=True)
    out = diversify(rows, per_brand=4, limit=20)
    assert [t[2]["restaurant_id"] for t in out] == [1, 1, 1, 1, 2], out
    assert [t[0] for t in out] == [100, 99, 98, 97, 50]  # 점수순 유지
    assert len(diversify(rows, per_brand=4, limit=3)) == 3
    assert diversify([], per_brand=4, limit=3) == []
    print("ok")
