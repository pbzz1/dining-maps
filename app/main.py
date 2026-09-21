"""FastAPI 앱 조립만 한다. 엔드포인트는 app/<기능>/router.py 에 있다."""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.router import router as auth_router
from app.menus.router import router as menus_router
from app.profile.router import router as profile_router
from app.new_menu.router import router as new_menu_router
from app.recommend.router import router as recommend_router
from app.restaurants.router import router as restaurants_router
from app.stats.router import router as stats_router
from app.stores.router import router as stores_router

app = FastAPI(title="Dining Maps API")

# The frontend is a separate Vite/React app on its own origin, so the API has to
# opt into cross-origin requests. Origins are listed explicitly rather than "*"
# -- add the deployed frontend URL via ALLOWED_ORIGINS (comma-separated) when
# deploying. In dev the Vite proxy makes requests same-origin anyway, but a
# direct browser call to :8000 still needs this.
DEFAULT_ALLOWED_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get("ALLOWED_ORIGINS", ",".join(DEFAULT_ALLOWED_ORIGINS)).split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    # 개인화(프로필 저장·행동 이벤트·탈퇴)가 생기면서 GET만으로는 부족해졌다.
    # Authorization 헤더가 프리플라이트 대상이라 OPTIONS도 열려 있어야 한다.
    # 인증은 Bearer 토큰이라 쿠키를 쓰지 않는다 -- allow_credentials는 그대로 꺼 둔다.
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

for r in (
    restaurants_router,
    stores_router,
    menus_router,
    stats_router,
    recommend_router,
    new_menu_router,
    auth_router,
    profile_router,
):
    app.include_router(r)

# No StaticFiles mount here on purpose: the frontend is now its own Vite/React
# app (frontend-react/) served separately. Mounting it at "/" also used to
# swallow every unmatched route, which made 404s from the API indistinguishable
# from missing static files.
