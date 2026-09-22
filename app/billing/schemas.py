from datetime import datetime

from pydantic import BaseModel, Field


class PlanOut(BaseModel):
    key: str
    label: str
    price_krw: int          # 부가세 포함, 30일
    model: str
    daily_limit: int


class CheckoutIn(BaseModel):
    plan: str = Field(pattern="^(standard|high)$")


class CheckoutOut(BaseModel):
    """토스 결제창을 열 때 필요한 값. amount 는 서버 요금제 설정에서만 나온다."""

    order_id: str
    order_name: str
    amount: int
    plan: str
    customer_key: str


class ConfirmIn(BaseModel):
    payment_key: str = Field(max_length=200)
    order_id: str = Field(max_length=64)
    amount: int


class EntitlementOut(BaseModel):
    plan: str
    starts_at: datetime
    ends_at: datetime
    ai_budget_left_pct: int


class BillingMeOut(BaseModel):
    plan: str                          # free / standard / high
    plan_ends_at: datetime | None
    ai_budget_left_pct: int | None     # 이번 이용권의 남은 AI 예산 비율. 무료면 None
    daily_limit: int | None
    used_today: int | None
    payments_enabled: bool             # 서버에 토스 키가 있는지 -- 없으면 결제 버튼을 비활성화한다
