from fastapi import APIRouter, Depends, HTTPException

from app.auth.deps import current_user
from app.db import get_connection
from app.recommend.goals import GOALS
from app.recommend.personal import personal_reco
from app.recommend.ranking import fetch_menus, nearest_stores, rank, to_out
from app.recommend.schemas import GoalOut, PersonalRecoOut, RecommendedMenuOut

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
    try:
        top = rank(fetch_menus(conn), goal, limits, exclude_drinks)[:limit]
        # 근처 매장: 상위 메뉴의 브랜드만 조회해서 브랜드별 최단 거리 1곳.
        nearest = nearest_stores(conn, {t[2]["restaurant_id"] for t in top}, lat, lng, radius_m)
    finally:
        conn.close()
    return [to_out(score, reason, row, nearest) for score, reason, row in top]


@router.get("/personal", response_model=PersonalRecoOut)
def recommend_personal(
    lat: float | None = None,
    lng: float | None = None,
    radius_m: int = 3000,
    user: dict = Depends(current_user),
):
    """로그인 사용자의 서버 프로필·행동 이력으로 고른 3개 + 한 줄 조언.
    위치는 서버에 저장하지 않으므로 매 요청 쿼리로 받는다 (/menus 와 같다)."""
    return personal_reco(user["id"], lat, lng, radius_m, use_llm=user.get("plan") == "premium")
