"""결제 없이 이용권을 발급·취소한다(운영자용). 결제 연동 전 검증과 수동 보상에 쓴다.

    DATABASE_URL=postgresql://... python scripts/billing/grant_entitlement.py --user 1 --plan standard
    DATABASE_URL=postgresql://... python scripts/billing/grant_entitlement.py --user 1 --status
    DATABASE_URL=postgresql://... python scripts/billing/grant_entitlement.py --user 1 --revoke

같은 요금제가 이미 유효하면 그 만료일 다음부터 시작한다(연장). 다른 요금제가 유효한 채로 발급하면
둘이 겹치고 먼저 시작한 쪽이 판정에 쓰이므로, 바꾸려면 --revoke 로 먼저 무효화한다.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from app.billing import budget  # noqa: E402
from app.billing.plans import PLANS  # noqa: E402
from app.db import connect  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", type=int, required=True, help="app_user.id")
    ap.add_argument("--plan", choices=sorted(PLANS), help="발급할 요금제")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--revoke", action="store_true", help="이 사용자의 유효한 이용권 전부 무효화")
    ap.add_argument("--status", action="store_true", help="지금 상태만 출력")
    a = ap.parse_args()
    with connect() as conn:
        if a.revoke:
            n = conn.execute(
                "UPDATE entitlement SET revoked_at = now() WHERE user_id = %s AND revoked_at IS NULL AND now() < ends_at",
                (a.user,),
            ).rowcount
            print(f"revoked {n}")
        if a.plan:
            row = budget.grant(conn, a.user, a.plan, days=a.days)
            print(f"granted {row['plan']} #{row['id']} {row['starts_at']:%Y-%m-%d} ~ {row['ends_at']:%Y-%m-%d} budget {row['budget_krw']}원")
        print(budget.status(conn, a.user))


if __name__ == "__main__":
    main()
