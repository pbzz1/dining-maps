"""보관 기간이 끝난 개인정보를 지운다. 매일 .github/workflows/privacy-purge.yml 이 돌린다.

개인정보 처리방침(/privacy/, scripts/build-static-pages.mjs privacyPage)의 2조가 약속한
기간을 코드로 지키는 곳이다. 기간을 바꾸면 두 군데를 같이 고친다.

  1. 결제 기록(paid/canceled, payment 테이블이 있을 때): 전자상거래법상 대금결제 기록 보관 5년이 지나면 삭제.
  2. 완료되지 않은 주문(ready/failed): 거래 기록이 아니라 보관 의무가 없다. 분쟁 확인용으로
     90일 두고 삭제.
  3. 별도 동의 없는 신체정보: 동의 기능이 생기기 전에 저장된 값, 또는 어떤 경로로든 동의 없이
     남은 값(app/auth/consent.py). 저장 경로는 이미 막혀 있으니 평소엔 0건이어야 한다.

    DATABASE_URL=postgresql://... python scripts/maintenance/purge_expired.py [--dry-run]
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from app.auth.consent import HEALTH_FIELDS  # noqa: E402
from app.db import apply_schema, connect  # noqa: E402

PAYMENT_YEARS = 5
UNFINISHED_DAYS = 90

EXPIRED_PAYMENTS = f"""
    SELECT order_id FROM payment
    WHERE (status IN ('paid', 'canceled') AND created_at < now() - interval '{PAYMENT_YEARS} years')
       OR (status IN ('ready', 'failed') AND created_at < now() - interval '{UNFINISHED_DAYS} days')
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="세기만 하고 지우지 않는다")
    args = ap.parse_args()

    with connect() as conn:
        apply_schema(conn)  # health_consent_at 이 아직 없는 DB에서 돌아도 되게
        unlinked = payments = 0
        # 결제 테이블은 유료 요금제(app/billing)와 함께 생긴다 -- 아직 없는 DB면 건너뛴다.
        if conn.execute("SELECT to_regclass('payment') IS NOT NULL AS ok").fetchone()["ok"]:
            # 이용권이 옛 결제를 가리키고 있으면 FK 때문에 결제를 못 지운다 -- 연결만 끊는다.
            # (5년 지난 이용권은 이미 끝났다. 이용권 자체는 탈퇴 때 CASCADE 로 지워진다.)
            unlinked = conn.execute(
                f"UPDATE entitlement SET payment_order_id = NULL WHERE payment_order_id IN ({EXPIRED_PAYMENTS})"
            ).rowcount
            payments = conn.execute(f"DELETE FROM payment WHERE order_id IN ({EXPIRED_PAYMENTS})").rowcount
        not_null = " OR ".join(f"p.{f} IS NOT NULL" for f in HEALTH_FIELDS)
        health = conn.execute(
            f"""UPDATE user_profile p SET {', '.join(f'{f} = NULL' for f in HEALTH_FIELDS)}, updated_at = now()
                FROM app_user u
                WHERE u.id = p.user_id AND u.health_consent_at IS NULL AND ({not_null})"""
        ).rowcount
        print(f"결제 기록 {payments}건 삭제(이용권 연결 해제 {unlinked}건) · 동의 없는 신체정보 {health}명분 삭제"
              + (" -- dry-run, 되돌림" if args.dry_run else ""))
        if args.dry_run:
            conn.rollback()


if __name__ == "__main__":
    main()
