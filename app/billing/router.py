"""결제·이용권 API.

    POST /api/billing/checkout  -- 주문번호·금액 발급(금액은 서버 설정만 쓴다)
    [프론트가 토스 결제창을 연다 -> 성공 리다이렉트]
    POST /api/billing/confirm   -- 토스 승인 API 호출, 금액·주문번호가 기록과 같을 때만 이용권 발급
    GET  /api/billing/me        -- 지금 요금제·만료일·남은 AI 예산 %
    GET  /api/billing/plans     -- 요금제 표(공개)
    POST /api/billing/webhook   -- 토스 웹훅. 취소·환불이면 이용권 즉시 무효화

같은 주문번호로 두 번 승인해도 이용권은 1개다(payment 행 잠금 + status 로 막는다).
업그레이드(이용권 사용 중 다른 요금제 구매)는 v1 에서 막는다 -- 남은 기간·예산을 어떻게 옮길지 정한 뒤 연다.
"""
import hashlib
import json
import os
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth.deps import current_user
from app.billing import budget, toss
from app.billing.plans import PLANS, get_plan
from app.billing.schemas import BillingMeOut, CheckoutIn, CheckoutOut, ConfirmIn, EntitlementOut, PlanOut
from app.db import connect, get_connection

router = APIRouter(prefix="/api/billing", tags=["billing"])


def _customer_key(user_id: int) -> str:
    # 토스 SDK 의 customerKey. 추측 불가능해야 해서 사용자 id 를 그대로 쓰지 않는다.
    secret = os.environ.get("JWT_SECRET", "")
    return "dm_" + hashlib.sha256(f"{secret}:{user_id}".encode()).hexdigest()[:32]


def _entitlement_out(ent: dict) -> EntitlementOut:
    return EntitlementOut(
        plan=ent["plan"], starts_at=ent["starts_at"], ends_at=ent["ends_at"],
        ai_budget_left_pct=budget.budget_left_pct(ent) or 0,
    )


@router.get("/plans", response_model=list[PlanOut])
def list_plans():
    return [PlanOut(key=p.key, label=p.label, price_krw=p.price_krw, model=p.model, daily_limit=p.daily_limit)
            for p in PLANS.values()]


@router.get("/me", response_model=BillingMeOut)
def billing_me(user: dict = Depends(current_user)):
    conn = get_connection()
    try:
        return BillingMeOut(
            **budget.status(conn, user["id"]), payments_enabled=toss.is_configured(),
            client_key=os.environ.get("TOSS_CLIENT_KEY") or None,
        )
    finally:
        conn.close()


@router.post("/checkout", response_model=CheckoutOut)
def checkout(body: CheckoutIn, user: dict = Depends(current_user)):
    if not toss.is_configured():
        raise HTTPException(status_code=503, detail="결제가 아직 준비되지 않았습니다.")
    plan = get_plan(body.plan)
    with connect() as conn:
        current = budget.active_entitlement(conn, user["id"])
        if current and current["plan"] != plan.key:
            raise HTTPException(status_code=409, detail="지금 쓰는 요금제가 끝난 뒤에 다른 요금제를 살 수 있어요.")
        order_id = "dm_" + secrets.token_urlsafe(18)
        conn.execute(
            "INSERT INTO payment (order_id, user_id, plan, amount, status) VALUES (%s, %s, %s, %s, 'ready')",
            (order_id, user["id"], plan.key, plan.price_krw),
        )
    return CheckoutOut(
        order_id=order_id, order_name=f"Dining Maps {plan.label} 30일", amount=plan.price_krw, plan=plan.key,
        customer_key=_customer_key(user["id"]),
    )


@router.post("/confirm", response_model=EntitlementOut)
def confirm(body: ConfirmIn, user: dict = Depends(current_user)):
    """토스 성공 리다이렉트 뒤 프론트가 부른다. 이용권은 여기서만 생긴다.

    실패를 기록하는 UPDATE 는 트랜잭션이 커밋된 뒤에 HTTPException 을 던진다 -- connect() 는 예외가 나면
    롤백하므로 with 안에서 던지면 '실패' 표시가 같이 사라져 같은 주문을 다시 승인할 수 있게 된다.
    """
    error = None
    with connect() as conn:
        # 같은 주문의 승인 요청 둘이 동시에 오면 뒤의 것은 여기서 기다렸다가 'paid' 를 본다.
        pay = conn.execute(
            "SELECT * FROM payment WHERE order_id = %s AND user_id = %s FOR UPDATE", (body.order_id, user["id"])
        ).fetchone()
        if pay is None:
            raise HTTPException(status_code=404, detail="없는 주문입니다.")
        if pay["status"] == "paid":
            # 멱등: 이미 처리된 주문이면 그 이용권을 그대로 돌려준다.
            ent = conn.execute("SELECT * FROM entitlement WHERE payment_order_id = %s", (body.order_id,)).fetchone()
            if ent:
                return _entitlement_out(ent)
        if pay["status"] != "ready":
            raise HTTPException(status_code=409, detail="이미 끝난 주문입니다.")
        if body.amount != pay["amount"]:
            # 프론트가 금액을 바꿔 보냈다. 승인하지 않고 주문을 닫는다.
            conn.execute("UPDATE payment SET status = 'failed' WHERE order_id = %s", (body.order_id,))
            error = (400, "결제 금액이 주문과 다릅니다.")
        else:
            try:
                result = toss.confirm(body.payment_key, body.order_id, pay["amount"])
            except toss.TossError as e:
                conn.execute(
                    "UPDATE payment SET status = 'failed', payment_key = %s, raw = %s WHERE order_id = %s",
                    (body.payment_key, json.dumps({"code": e.code, "message": str(e)}), body.order_id),
                )
                error = (402, str(e))
            else:
                # 토스 응답도 한 번 더 대조한다 -- 승인 API 가 다른 주문의 결과를 줄 리는 없지만 돈이 걸린 자리다.
                if result.get("orderId") != body.order_id or int(result.get("totalAmount", -1)) != pay["amount"]:
                    raise HTTPException(status_code=502, detail="토스 승인 응답이 주문과 다릅니다.")
                conn.execute(
                    """UPDATE payment SET status = 'paid', payment_key = %s, approved_at = now(), raw = %s
                       WHERE order_id = %s""",
                    (body.payment_key, json.dumps(result, ensure_ascii=False), body.order_id),
                )
                ent = budget.grant(conn, user["id"], pay["plan"], order_id=body.order_id)
    if error:
        raise HTTPException(status_code=error[0], detail=error[1])
    return _entitlement_out(ent)


@router.post("/webhook")
async def webhook(request: Request):
    """토스 결제 상태 변경 웹훅. 본문에 서명이 없으므로 paymentKey 로 토스에 다시 물어본 상태만 믿는다.
    취소·환불·만료면 이용권을 즉시 무효화한다. 토스는 2xx 가 아니면 재전송하므로 모르는 이벤트도 200."""
    if not toss.is_configured():
        raise HTTPException(status_code=503, detail="결제가 설정되지 않았습니다.")
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="JSON 이 아닙니다.")
    data = body.get("data") or {}
    payment_key, order_id = data.get("paymentKey"), data.get("orderId")
    if not payment_key or not order_id:
        return {"ok": True, "ignored": True}
    try:
        payment = toss.fetch_payment(payment_key)
    except toss.TossError as e:
        # 조회가 안 되면 처리하지 않는다 -- 500 을 주면 토스가 다시 보낸다.
        raise HTTPException(status_code=502, detail=str(e)) from e
    if payment.get("orderId") != order_id:
        return {"ok": True, "ignored": True}
    revoked = 0
    if payment.get("status") in toss.REVOKING_STATUSES:
        with connect() as conn:
            conn.execute(
                "UPDATE payment SET status = 'canceled', raw = %s WHERE order_id = %s AND payment_key = %s",
                (json.dumps(payment, ensure_ascii=False), order_id, payment_key),
            )
            revoked = budget.revoke_by_order(conn, order_id)
    return {"ok": True, "revoked": revoked}
