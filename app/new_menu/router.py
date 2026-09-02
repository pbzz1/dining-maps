"""신메뉴 피드: menu_change_log의 'added' 행이 곧 신메뉴 감지기다.

별도 크롤이나 감지 로직을 만들지 않는다 -- snapshot_and_validate.py가 매 크롤마다
이전 스냅샷과 diff해서 added/removed/changed를 이미 기록하고 있고, 그중
change_type='added' AND verdict='real_change'가 "브랜드가 실제로 새로 올린 메뉴"다.
LLM 리뷰(다이어트 판정 + 예상 맛)는 scripts/llm/generate_new_menu_reviews.py가
배치로 채우는 캐시(new_menu_review)를 조인만 한다 -- 런타임 LLM 호출 없음.
"""
from fastapi import APIRouter

from app.db import get_connection
from app.new_menu.schemas import NewMenuOut

router = APIRouter(prefix="/api", tags=["new-menu"])

# 한 크롤에서 한 브랜드가 이보다 많은 메뉴를 한꺼번에 'added'로 올렸다면 신메뉴가
# 아니라 브랜드 신규 온보딩(크롤러에 브랜드 추가)이다. 브랜드는 신메뉴를 한 번에
# 몇 개씩만 내지, 수십 개를 내지 않는다.
# ponytail: 고정 컷 15 -- 온보딩/신메뉴를 나누는 더 똑똑한 기준이 필요해지면 조정.
ONBOARDING_CAP = 15

# 이보다 오래된 것은 더이상 "신"메뉴가 아니다.
WINDOW_DAYS = 90

# 한 브랜드가 피드를 독식하지 않게 브랜드당 메뉴 수 제한. 사이즈·세트 옵션은
# base_name으로 묶여 한 메뉴로 세므로(아래 OPTION_SUFFIX_RE) 도미노의 L/M 두 행이
# 슬롯 두 개를 먹지 않는다. 크러스트 조합처럼 이름 본체가 다른 것은 여전히 별개 메뉴.
PER_BRAND_CAP = 5

# 옵션 행까지 합치면 한 브랜드가 몇십 행이 될 수 있어 행 수에도 상한을 둔다.
PER_BRAND_ROW_CAP = 15

# 브랜드가 같은 메뉴를 옵션마다 다른 행으로 준다: "…크루아상위치 / …세트 / …라지세트",
# "…나폴리 L / M", "펩시콜라(L) / (R)". 이 접미사를 떼어낸 것이 base_name이고,
# 프론트는 그 키로 한 줄에 묶어 옵션 칩으로 보여준다. 규칙은 여기 한 곳에만 둔다.
# ponytail: 사이즈·세트만 -- HOT/ICED·콘/컵도 묶고 싶어지면 이 정규식에 추가.
OPTION_SUFFIX_RE = r"\s*[(（](L|M|R|S|대|중|소)[)）]$|\s+(라지\s?세트|세트|라지|미디엄|레귤러|스몰|L|M|R|S)$"

# 라우터와 배치 스크립트(generate_new_menu_reviews.py)가 같은 "신메뉴" 정의를
# 공유해야 해서 쿼리를 모듈 상수로 둔다. 파라미터: limit 하나.
#
# "신메뉴 날짜"는 released_at(보도자료 확인 실제 출시일, seed_released_at.py)이
# 우선이고, 없으면 크롤 diff의 첫 발견일이다. released_at이 있는데 오래됐다면
# 뒤늦게 크롤에 잡혔어도 신메뉴가 아니므로 COALESCE 하나로 둘 다 처리된다.
NEW_MENUS_SQL = f"""
WITH added_events AS (
    SELECT mcl.run_id, mcl.restaurant_name, mcl.menu_name, cr.started_at
    FROM menu_change_log mcl
    JOIN crawl_run cr ON cr.id = mcl.run_id AND cr.status = 'passed'
    WHERE mcl.change_type = 'added' AND mcl.verdict = 'real_change'
), sane AS (
    SELECT run_id, restaurant_name FROM added_events
    GROUP BY run_id, restaurant_name
    HAVING COUNT(*) <= {ONBOARDING_CAP}
), added AS (
    -- 같은 메뉴가 빠졌다 다시 들어오면 added가 여러 번 쌓인다 -> 가장 최근 것만.
    SELECT ae.restaurant_name, ae.menu_name, MAX(ae.started_at) AS first_seen_at
    FROM added_events ae JOIN sane s USING (run_id, restaurant_name)
    GROUP BY ae.restaurant_name, ae.menu_name
), named AS (
    SELECT mi.id, mi.restaurant_id, a.first_seen_at,
           COALESCE(mi.released_at, a.first_seen_at::date) AS event_date,
           regexp_replace(mi.name, '{OPTION_SUFFIX_RE}', '') AS base_name
    FROM menu_item mi
    JOIN restaurant r ON r.id = mi.restaurant_id
    LEFT JOIN added a ON a.restaurant_name = r.name AND a.menu_name = mi.name
    WHERE COALESCE(mi.released_at, a.first_seen_at::date)
          > (now() - interval '{WINDOW_DAYS} days')::date
), fresh AS (
    -- 브랜드 슬롯은 base_name(=옵션 뗀 메뉴) 단위로 센다. 같은 메뉴의 옵션들은
    -- 같은 크롤에서 함께 잡혀 event_date가 같으므로 한 rank에 모인다.
    SELECT n.*,
           DENSE_RANK() OVER (
               PARTITION BY restaurant_id ORDER BY event_date DESC, base_name
           ) AS brand_rank,
           ROW_NUMBER() OVER (
               PARTITION BY restaurant_id ORDER BY event_date DESC, base_name, id
           ) AS brand_row
    FROM named n
), brand_pct AS (
    -- "이 신메뉴가 그 브랜드의 같은 카테고리 안에서 칼로리·단백질이 어느 위치인가".
    -- 브랜드 전체와 비교하면 버거 브랜드의 음료가 늘 '저칼로리 1위'가 되므로
    -- 같은 category_group 안에서만 줄 세운다. 0 = 최저, 100 = 최고.
    SELECT nf2.menu_item_id, nf2.nutrient_name,
           ROUND((PERCENT_RANK() OVER (
               PARTITION BY mi2.restaurant_id, mi2.category_group, nf2.nutrient_name
               ORDER BY nf2.value
           ) * 100)::numeric, 0) AS pct
    FROM nutrition_fact nf2
    JOIN menu_item mi2 ON mi2.id = nf2.menu_item_id
    WHERE nf2.nutrient_name IN ('calorie', 'protein')
)
SELECT mi.id, mi.name, f.base_name, r.id AS restaurant_id, r.name AS restaurant_name,
       mi.category_group, mi.weight_g, mi.total_weight_g, mi.nutrition_basis, mi.image_url, mi.youtube_video_id,
       f.event_date, mi.released_at, f.first_seen_at,
       ds.score AS diet_score, ds.absolute_grade,
       MAX(bp.pct) FILTER (WHERE bp.nutrient_name = 'calorie') AS calorie_brand_pct,
       MAX(bp.pct) FILTER (WHERE bp.nutrient_name = 'protein') AS protein_brand_pct,
       MAX(nf.value) FILTER (WHERE nf.nutrient_name = 'calorie')       AS calorie,
       MAX(nf.value) FILTER (WHERE nf.nutrient_name = 'protein')       AS protein,
       MAX(nf.value) FILTER (WHERE nf.nutrient_name = 'sugar')         AS sugar,
       MAX(nf.value) FILTER (WHERE nf.nutrient_name = 'saturated_fat') AS saturated_fat,
       MAX(nf.value) FILTER (WHERE nf.nutrient_name = 'sodium')        AS sodium,
       rv.diet_verdict, rv.diet_comment, rv.taste_note
FROM fresh f
JOIN menu_item mi  ON mi.id = f.id
JOIN restaurant r  ON r.id = mi.restaurant_id
LEFT JOIN diet_score ds      ON ds.menu_item_id = mi.id
LEFT JOIN nutrition_fact nf  ON nf.menu_item_id = mi.id
LEFT JOIN brand_pct bp       ON bp.menu_item_id = mi.id
LEFT JOIN new_menu_review rv ON rv.menu_item_id = mi.id
WHERE f.brand_rank <= {PER_BRAND_CAP} AND f.brand_row <= {PER_BRAND_ROW_CAP}
GROUP BY mi.id, mi.name, f.base_name, r.id, r.name, mi.category_group, mi.weight_g,
         mi.total_weight_g, mi.nutrition_basis, mi.image_url, mi.youtube_video_id, f.event_date, mi.released_at,
         f.first_seen_at, ds.score, ds.absolute_grade,
         rv.diet_verdict, rv.diet_comment, rv.taste_note
ORDER BY f.event_date DESC, r.name, f.base_name, mi.id
LIMIT %s
"""


def fetch_new_menus(conn, limit: int = 30):
    return conn.execute(NEW_MENUS_SQL, (limit,)).fetchall()


@router.get("/new-menus", response_model=list[NewMenuOut])
def list_new_menus(limit: int = 30):
    limit = max(1, min(limit, 100))
    conn = get_connection()
    rows = fetch_new_menus(conn, limit)
    conn.close()
    return [NewMenuOut(**_as_whole_item(dict(r))) for r in rows]


NUTRIENT_KEYS = ("calorie", "protein", "sugar", "saturated_fat", "sodium")


def _as_whole_item(r: dict) -> dict:
    """신메뉴 화면은 '한 마리·한 판' 기준으로 보여준다 -- 사람들이 보는 건 "100g당
    353kcal"이나 "1회분 360kcal"이 아니라 통째 값이다. 두 경우를 환산한다:
      per_100g  (교촌·BHC)  x weight_g/100        -- 제품 중량이 있을 때
      per_serving + total_weight_g (도미노 150g/한 판) x total/weight_g
    환산하면 weight_g도 통째 중량으로 바꿔 프론트가 "총 1,248g"으로 단다.
    근거(중량)가 없으면 손대지 않고 프론트가 원래 기준을 표시한다.
    점수·추천·탐색기는 이 함수를 거치지 않으므로 원래 기준 그대로다."""
    r["event_date"] = r["event_date"].isoformat()
    r["released_at"] = r["released_at"].isoformat() if r["released_at"] else None
    r["first_seen_at"] = r["first_seen_at"].date().isoformat() if r["first_seen_at"] else None
    factor, total = None, None
    if r["nutrition_basis"] == "per_100g" and r["weight_g"]:
        factor, total = r["weight_g"] / 100, r["weight_g"]
    elif r["weight_g"] and r.get("total_weight_g") and r["total_weight_g"] > r["weight_g"]:
        factor, total = r["total_weight_g"] / r["weight_g"], r["total_weight_g"]
    r["scaled_to_total"] = factor is not None
    if factor:
        for k in NUTRIENT_KEYS:
            if r[k] is not None:
                r[k] = round(r[k] * factor, 1)
        r["weight_g"] = total
    return r


if __name__ == "__main__":
    # OPTION_SUFFIX_RE 자체 점검. Postgres ARE와 Python re는 이 패턴 범위에서 같다.
    import re

    base = lambda n: re.sub(OPTION_SUFFIX_RE, "", n)  # noqa: E731
    assert base("데리야킹 크리스퍼 라지세트") == "데리야킹 크리스퍼"
    assert base("데리야킹 크리스퍼 세트") == "데리야킹 크리스퍼"
    assert base("데리야킹 크리스퍼") == "데리야킹 크리스퍼"
    assert base("무진장 슈림프 스테이크 나폴리 L") == "무진장 슈림프 스테이크 나폴리"
    assert base("펩시콜라(L)") == "펩시콜라"
    assert base("마구마구 밤식빵(대)") == "마구마구 밤식빵"
    assert base("후렌치 후라이 미디엄") == "후렌치 후라이"
    # 옵션이 아닌 것은 건드리지 않는다: 이름 본체가 다르면 별개 메뉴.
    assert base("무진장 슈림프 스테이크 고구마쥬 엣지(오)") == "무진장 슈림프 스테이크 고구마쥬 엣지(오)"
    assert base("아이스 카페라떼") == "아이스 카페라떼"
    assert base("밀크 아이스크림 (컵)") == "밀크 아이스크림 (컵)"
    print("ok")
