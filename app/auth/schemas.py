from datetime import datetime

from pydantic import BaseModel


class MeOut(BaseModel):
    id: int
    provider: str
    nickname: str | None
    created_at: datetime
    # free | standard | high -- 지금 유효한 이용권에서 계산한다(app/billing). 프론트가 유료 기능 안내를 띄울지 정한다.
    plan: str = "free"
    plan_ends_at: datetime | None = None
    ai_budget_left_pct: int | None = None  # 이번 이용권의 남은 AI 예산 %(유료만)


class AuthStatusOut(BaseModel):
    # 서버에 카카오 키가 안 꽂혀 있으면 프론트가 로그인 버튼을 숨긴다 --
    # 눌러야만 안 되는 걸 아는 버튼은 없는 것만 못하다.
    enabled: bool
    provider: str
