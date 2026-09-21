"""로그인 라우트. 브라우저 리다이렉트 왕복이라 JSON API와 성격이 다르다.

    프론트 "카카오로 로그인" -> GET /api/auth/kakao/login
      -> 302 카카오 동의화면 -> 카카오가 code를 붙여 /api/auth/kakao/callback 호출
      -> 사용자 upsert + 우리 JWT 발급 -> 302 프론트?token=... 로 돌려보냄

토큰을 httpOnly 쿠키가 아니라 URL 쿼리로 넘기는 이유: 프론트(CloudFront)와
API(Lambda Function URL)가 서로 다른 오리진이라 쿠키를 쓰면 서드파티 쿠키가 되고,
요즘 브라우저는 그걸 기본 차단한다. 프론트가 받는 즉시 localStorage에 옮기고
history.replaceState로 주소창에서 지운다 (features/auth/useAuth.js).
"""
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse

from app.auth import kakao, tokens
from app.auth.deps import current_user
from app.auth.schemas import AuthStatusOut, MeOut
from app.db import connect

router = APIRouter(prefix="/api/auth", tags=["auth"])

# state 는 서버에 저장하지 않고 서명해서 카카오에 맡겼다가 돌려받는다 -- Lambda는
# 요청 간 메모리를 공유하지 않고, 이거 하나 때문에 세션 테이블을 만들 이유는 없다.
STATE_TTL_SECONDS = 600


def frontend_url() -> str:
    # 기본값을 두지 않는다. 예전엔 localhost:5173 이 기본값이라 운영에서 이 값 하나가
    # 빠지자 로그인은 성공하고 토큰이 개발용 주소로 날아갔다. 없으면 로그인 자체를 끈다
    # (auth_status). 로컬 개발은 .env 에 FRONTEND_URL=http://localhost:5173 을 넣는다.
    return os.environ["FRONTEND_URL"].rstrip("/")


def _issue_state() -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"n": secrets.token_urlsafe(8), "exp": now + timedelta(seconds=STATE_TTL_SECONDS)},
        tokens.get_secret(),
        algorithm=tokens.ALGORITHM,
    )


def _valid_state(state: str) -> bool:
    try:
        jwt.decode(state, tokens.get_secret(), algorithms=[tokens.ALGORITHM])
        return True
    except jwt.PyJWTError:
        return False


@router.get("/status", response_model=AuthStatusOut)
def auth_status():
    enabled = kakao.is_configured() and all(os.environ.get(k) for k in ("JWT_SECRET", "FRONTEND_URL"))
    return AuthStatusOut(enabled=enabled, provider=kakao.PROVIDER)


@router.get("/kakao/login")
def kakao_login():
    # 콜백이 돌아갈 곳을 모르면 카카오 동의까지 받아 놓고 500을 내게 된다. 출발 전에 막는다.
    if not os.environ.get("FRONTEND_URL"):
        raise HTTPException(status_code=503, detail="FRONTEND_URL 환경변수가 없어 로그인을 쓸 수 없습니다.")
    try:
        return RedirectResponse(kakao.authorize_url(_issue_state()), status_code=302)
    except (kakao.KakaoError, tokens.AuthConfigError) as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@router.get("/kakao/callback")
def kakao_callback(code: str | None = None, state: str | None = None, error: str | None = None):
    """카카오에서 돌아오는 자리. 실패도 프론트로 돌려보낸다 -- 사용자가 API의
    JSON 오류 화면에 덩그러니 남으면 앱으로 돌아올 길이 없다."""
    if error or not code:
        # error 값은 카카오가 준 문자열이라 그대로 붙이지 않는다 (오픈 리다이렉트/XSS 방지).
        return RedirectResponse(f"{frontend_url()}/?auth_error=1", status_code=302)
    if not state or not _valid_state(state):
        return RedirectResponse(f"{frontend_url()}/?auth_error=1", status_code=302)

    try:
        uid, nickname = kakao.fetch_profile(kakao.exchange_code(code))
    except kakao.KakaoError as e:
        print(f"kakao login failed: {e}")
        return RedirectResponse(f"{frontend_url()}/?auth_error=1", status_code=302)

    with connect() as conn:
        # 닉네임은 매 로그인마다 덮어쓴다 -- 카카오에서 바꾼 이름이 여기만 옛날 것으로
        # 남으면 "내 계정이 맞나" 싶어진다. ON CONFLICT 로 가입/재로그인을 한 문장에.
        row = conn.execute(
            """INSERT INTO app_user (provider, provider_uid, nickname, last_login_at)
               VALUES (%s, %s, %s, now())
               ON CONFLICT (provider, provider_uid)
               DO UPDATE SET nickname = EXCLUDED.nickname, last_login_at = now()
               RETURNING id""",
            (kakao.PROVIDER, uid, nickname),
        ).fetchone()

    return RedirectResponse(f"{frontend_url()}/?token={tokens.issue(row['id'])}", status_code=302)


@router.get("/me", response_model=MeOut)
def me(user: dict = Depends(current_user)):
    return MeOut(**user)
