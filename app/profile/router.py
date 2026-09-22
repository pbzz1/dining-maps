"""이 서비스의 첫 쓰기 API. 전부 로그인이 필요하다.

프로필은 행이 없을 수도 있다(가입 직후) -- GET은 404 대신 전 필드 None인 빈
프로필을 준다. 프론트가 "없음"과 "못 불러옴"을 구분하느라 분기를 늘릴 이유가 없다.
"""
from fastapi import APIRouter, Depends, HTTPException, Response

from app.auth import consent
from app.auth.deps import current_user
from app.db import connect, get_connection
from app.profile.schemas import EventIn, FavoriteOut, ProfileIn, ProfileOut

router = APIRouter(prefix="/api", tags=["profile"])

FIELDS = tuple(ProfileIn.model_fields)


@router.get("/profile", response_model=ProfileOut)
def get_profile(user: dict = Depends(current_user)):
    conn = get_connection()
    try:
        row = conn.execute(
            f"SELECT {', '.join(FIELDS)} FROM user_profile WHERE user_id = %s", (user["id"],)
        ).fetchone()
        if row and not consent.has_health_consent(conn, user["id"]):
            row = consent.strip_health(row)
    finally:
        conn.close()
    return ProfileOut(**row) if row else ProfileOut()


@router.put("/profile", response_model=ProfileOut)
def put_profile(payload: ProfileIn, user: dict = Depends(current_user)):
    """부분 갱신이 아니라 통째로 교체한다 -- 프론트는 어차피 폼 전체를 들고 있고,
    PATCH 로 하면 '값을 지웠다'와 '안 보냈다'를 구분할 수 없다."""
    columns = ", ".join(FIELDS)
    placeholders = ", ".join(["%s"] * len(FIELDS))
    updates = ", ".join(f"{f} = EXCLUDED.{f}" for f in FIELDS)
    with connect() as conn:
        # 별도 동의 전의 신체정보는 받아도 버린다 -- 프론트가 막지만 서버가 마지막 선이다.
        if not consent.has_health_consent(conn, user["id"]):
            payload = ProfileIn(**consent.strip_health(payload.model_dump()))
        values = [getattr(payload, f) for f in FIELDS]
        conn.execute(
            f"""INSERT INTO user_profile (user_id, {columns}, updated_at)
                VALUES (%s, {placeholders}, now())
                ON CONFLICT (user_id) DO UPDATE SET {updates}, updated_at = now()""",
            [user["id"], *values],
        )
    return payload


@router.post("/events", status_code=204, response_class=Response)
def post_event(payload: EventIn, user: dict = Depends(current_user)):
    """추천 카드를 눌렀다/숨겼다 같은 신호. 응답 본문이 없다 -- 프론트는 이 호출의
    결과를 기다리지도, 실패해도 화면을 바꾸지도 않는다(개인화는 부가 기능이다)."""
    with connect() as conn:
        impression_id = payload.impression_id
        if impression_id is not None:
            # 남의 노출 id 를 붙이면 그 사람의 학습 데이터를 오염시킬 수 있다 -- 내 것이 아니면 떼어 낸다.
            # 이벤트 자체는 남긴다(행동은 진짜이고, 연결만 믿을 수 없을 뿐이다).
            owned = conn.execute(
                "SELECT 1 FROM reco_impression WHERE id = %s AND user_id = %s", (impression_id, user["id"])
            ).fetchone()
            if not owned:
                impression_id = None
        conn.execute(
            """INSERT INTO user_event (user_id, menu_item_id, event_type, impression_id, surface, position)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (user["id"], payload.menu_item_id, payload.event_type, impression_id, payload.surface, payload.position),
        )
    return Response(status_code=204)


# 즐겨찾기는 따로 테이블이 없다 -- 추천 카드의 "저장"이 남긴 user_event(save)가 곧 즐겨찾기다.
# 같은 메뉴를 나중에 "이 메뉴 빼기"(hide) 했으면 목록에서 뺀다. 개인 추천(personal.load_history)이
# saved 에서 hidden 을 빼는 것과 같은 판단이되, 여기선 순서를 본다 -- 뺀 뒤 다시 저장했으면 즐겨찾기다.
FAVORITE_LIMIT = 200


@router.get("/favorites", response_model=list[FavoriteOut])
def list_favorites(user: dict = Depends(current_user)):
    conn = get_connection()
    try:
        rows = conn.execute(
            """WITH last AS (
                   SELECT menu_item_id,
                          MAX(created_at) FILTER (WHERE event_type = 'save') AS saved_at,
                          MAX(created_at) FILTER (WHERE event_type = 'hide') AS hidden_at
                   FROM user_event
                   WHERE user_id = %s AND menu_item_id IS NOT NULL AND event_type IN ('save', 'hide')
                   GROUP BY menu_item_id
               ), fav AS (
                   SELECT menu_item_id, saved_at FROM last
                   WHERE saved_at IS NOT NULL AND (hidden_at IS NULL OR hidden_at < saved_at)
               ), n AS (
                   SELECT menu_item_id,
                          MAX(value) FILTER (WHERE nutrient_name = 'calorie')       AS calorie,
                          MAX(value) FILTER (WHERE nutrient_name = 'protein')       AS protein,
                          MAX(value) FILTER (WHERE nutrient_name = 'sugar')         AS sugar,
                          MAX(value) FILTER (WHERE nutrient_name = 'saturated_fat') AS saturated_fat,
                          MAX(value) FILTER (WHERE nutrient_name = 'sodium')        AS sodium
                   FROM nutrition_fact
                   WHERE menu_item_id IN (SELECT menu_item_id FROM fav)
                   GROUP BY menu_item_id
               )
               SELECT mi.id AS menu_item_id, mi.name, r.name AS restaurant_name,
                      COALESCE(mi.category_group, '기타') AS category, mi.price_krw,
                      n.calorie, n.protein, n.sugar, n.saturated_fat, n.sodium, fav.saved_at
               FROM fav
               JOIN menu_item mi  ON mi.id = fav.menu_item_id
               JOIN restaurant r  ON r.id = mi.restaurant_id
               LEFT JOIN n        ON n.menu_item_id = mi.id
               ORDER BY fav.saved_at DESC, mi.id
               LIMIT %s""",
            (user["id"], FAVORITE_LIMIT),
        ).fetchall()
    finally:
        conn.close()
    return [FavoriteOut(**r) for r in rows]


@router.delete("/favorites/{menu_item_id}", status_code=204, response_class=Response)
def delete_favorite(menu_item_id: int, user: dict = Depends(current_user)):
    """즐겨찾기 해제 = 그 메뉴의 save 이벤트를 지운다. user_event 는 append-only 가 원칙이지만
    '저장 취소'를 새 이벤트로 쌓으면 학습형 추천(taste.py)과 개인 추천이 여전히 저장으로 읽는다 --
    사용자가 거둬들인 신호는 학습에서도 빠지는 게 맞다."""
    with connect() as conn:
        deleted = conn.execute(
            "DELETE FROM user_event WHERE user_id = %s AND menu_item_id = %s AND event_type = 'save'",
            (user["id"], menu_item_id),
        ).rowcount
    if not deleted:
        raise HTTPException(status_code=404, detail="즐겨찾기에 없는 메뉴입니다.")
    return Response(status_code=204)


@router.delete("/me", status_code=204, response_class=Response)
def delete_me(user: dict = Depends(current_user)):
    """탈퇴. user_profile·user_event 는 ON DELETE CASCADE 로 같이 지워진다.
    신체정보를 받는 이상 지우는 길도 같은 단계에서 있어야 한다."""
    with connect() as conn:
        conn.execute("DELETE FROM app_user WHERE id = %s", (user["id"],))
    return Response(status_code=204)
