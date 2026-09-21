"""이 서비스의 첫 쓰기 API. 전부 로그인이 필요하다.

프로필은 행이 없을 수도 있다(가입 직후) -- GET은 404 대신 전 필드 None인 빈
프로필을 준다. 프론트가 "없음"과 "못 불러옴"을 구분하느라 분기를 늘릴 이유가 없다.
"""
from fastapi import APIRouter, Depends, Response

from app.auth.deps import current_user
from app.db import connect, get_connection
from app.profile.schemas import EventIn, ProfileIn, ProfileOut

router = APIRouter(prefix="/api", tags=["profile"])

FIELDS = tuple(ProfileIn.model_fields)


@router.get("/profile", response_model=ProfileOut)
def get_profile(user: dict = Depends(current_user)):
    conn = get_connection()
    try:
        row = conn.execute(
            f"SELECT {', '.join(FIELDS)} FROM user_profile WHERE user_id = %s", (user["id"],)
        ).fetchone()
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
    values = [getattr(payload, f) for f in FIELDS]
    with connect() as conn:
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


@router.delete("/me", status_code=204, response_class=Response)
def delete_me(user: dict = Depends(current_user)):
    """탈퇴. user_profile·user_event 는 ON DELETE CASCADE 로 같이 지워진다.
    신체정보를 받는 이상 지우는 길도 같은 단계에서 있어야 한다."""
    with connect() as conn:
        conn.execute("DELETE FROM app_user WHERE id = %s", (user["id"],))
    return Response(status_code=204)
