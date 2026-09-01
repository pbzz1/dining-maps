from fastapi import APIRouter, HTTPException

from app.db import get_connection
from app.menus.schemas import MenuRankOut
from app.recommend.goals import MIN_CALORIE

router = APIRouter(prefix="/api/menus", tags=["menus"])

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


@router.get("", response_model=list[MenuRankOut])
def list_menus(
    sort: str = "calorie_desc",
    category: str | None = None,
    restaurant_id: int | None = None,
    q: str | None = None,
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
    if q and q.strip():
        # 메뉴 이름 부분일치. LIKE 와일드카드(%/_)는 검색어가 아니라 문자로 취급한다.
        escaped = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        where.append("mi.name ILIKE %s")
        params.append(f"%{escaped}%")

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
