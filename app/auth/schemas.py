from datetime import datetime

from pydantic import BaseModel


class MeOut(BaseModel):
    id: int
    provider: str
    nickname: str | None
    created_at: datetime
    plan: str = "free"  # free | premium -- 프론트가 유료 기능 안내를 띄울지 정한다


class AuthStatusOut(BaseModel):
    # 서버에 카카오 키가 안 꽂혀 있으면 프론트가 로그인 버튼을 숨긴다 --
    # 눌러야만 안 되는 걸 아는 버튼은 없는 것만 못하다.
    enabled: bool
    provider: str
