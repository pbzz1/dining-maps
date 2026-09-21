"""db/schema.sql 을 한 번 적용한다.

지금까지는 크롤/적재 잡(load_data.py 등)이 매 실행 전에 apply_schema()를 부르는
것만으로 충분했다 -- 새 테이블이 하루 한 번 크롤과 함께 생겨도 문제가 없었다.
API가 쓰는 테이블(app_user 등)은 다르다. 배포 직후 크롤 전까지 로그인이 전부
500이 된다. 그래서 배포 시점에 명시적으로 부를 수 있는 입구를 따로 둔다.

    DATABASE_URL=postgresql://... python scripts/migrate/apply_schema.py

schema.sql 이 전부 IF NOT EXISTS 라 몇 번을 돌려도 안전하다.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from app.db import apply_schema, connect  # noqa: E402


def main() -> None:
    with connect() as conn:
        apply_schema(conn)
    print("schema applied")


if __name__ == "__main__":
    main()
