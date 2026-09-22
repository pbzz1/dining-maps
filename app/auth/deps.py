"""FastAPI 의존성: 요청의 Bearer 토큰 -> 사용자 행.

optional_user 가 이 파일의 핵심이다. 이 서비스는 로그인 없이도 전부 동작하는 게
전제라서, 개인화 엔드포인트도 "로그인했으면 더 잘 맞춰주고, 아니면 기존 룰대로"가
되어야 한다. 401로 막는 건 프로필/이벤트처럼 쓸 사람이 특정돼야만 의미 있는 곳뿐이다.
"""
from fastapi import Depends, HTTPException, Request

from app.auth import tokens
from app.db import get_connection


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization") or ""
    scheme, _, token = header.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


def optional_user(request: Request) -> dict | None:
    """토큰이 없거나 쓸모없으면 None. 예외를 던지지 않는다."""
    token = _bearer(request)
    if not token:
        return None
    try:
        user_id = tokens.read_user_id(token)
    except tokens.AuthConfigError:
        # 서버에 JWT_SECRET이 없는 상태. 비로그인으로 취급해 화면은 계속 뜨게 한다.
        return None
    if user_id is None:
        return None
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT id, provider, nickname, created_at, plan, health_consent_at FROM app_user WHERE id = %s", (user_id,)
        ).fetchone()
    finally:
        conn.close()


def current_user(user: dict | None = Depends(optional_user)) -> dict:
    """로그인이 반드시 필요한 엔드포인트용."""
    if user is None:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    return user
