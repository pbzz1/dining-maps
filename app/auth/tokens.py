"""자체 세션 토큰(JWT) 발급/검증.

카카오가 준 액세스 토큰을 그대로 클라이언트에 돌려주지 않는다 -- 그 토큰은 카카오
API 호출 권한이라 우리 API 인증에 쓰기엔 과하고, 만료·갱신 주기도 우리가 못 정한다.
로그인 순간 한 번만 쓰고 버린 뒤, 우리가 서명한 토큰으로 바꿔서 내보낸다.

JWT_SECRET 이 없으면 앱이 뜨지 않는다 -- 기본값을 두면 그 기본값으로 서명된 토큰을
누구나 만들 수 있다. 다만 import 시점이 아니라 발급/검증 시점에 확인한다: 키가 없는
로컬/CI에서도 비로그인 경로(기존 기능 전부)는 그대로 떠야 하기 때문.
"""
import os
from datetime import datetime, timedelta, timezone

import jwt

ALGORITHM = "HS256"
# 한 끼 고를 때만 잠깐 여는 앱이라 재로그인이 잦으면 그대로 이탈한다. 길게 잡는다.
TOKEN_TTL_DAYS = 30


class AuthConfigError(RuntimeError):
    """JWT_SECRET 미설정. 401이 아니라 500이어야 한다 -- 사용자 잘못이 아니다."""


def get_secret() -> str:
    secret = os.environ.get("JWT_SECRET")
    if not secret:
        raise AuthConfigError("JWT_SECRET 환경변수가 없어 로그인 기능을 쓸 수 없습니다.")
    return secret


def issue(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": str(user_id), "iat": now, "exp": now + timedelta(days=TOKEN_TTL_DAYS)},
        get_secret(),
        algorithm=ALGORITHM,
    )


def read_user_id(token: str) -> int | None:
    """토큰이 유효하면 user_id, 아니면 None.

    만료/위조/형식오류를 구분하지 않는다 -- 호출부가 할 일은 어느 쪽이든 '다시
    로그인'으로 같고, 구분해서 알려주면 공격자에게만 정보가 된다.
    """
    try:
        payload = jwt.decode(token, get_secret(), algorithms=[ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
