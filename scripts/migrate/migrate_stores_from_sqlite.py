"""옛 SQLite(db/dining.db)의 store 4천여 행을 Postgres로 옮긴다.

Kakao 그리드 재크롤링(그리드 200여 점 x 브랜드 수 = 수천 콜, 수 시간)을 다시
돌릴 이유가 없다. 두 스키마의 store 컬럼이 동일하고, 다른 건 restaurant_id뿐이라
브랜드명으로 매핑만 해주면 그대로 들어간다.

    DATABASE_URL=postgresql://... python scripts/migrate/migrate_stores_from_sqlite.py

SQLite에 없는 신규 브랜드(BHC, 스타벅스 등)는 여전히 매장 데이터가 없다.
그건 KAKAO_REST_API_KEY 받아서 fetch_store_locations_nationwide.py로 채워야 한다.
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from app.db import connect  # noqa: E402

SQLITE_PATH = ROOT / "db" / "dining.db"

UPSERT = """
INSERT INTO store (restaurant_id, branch_name, address, lat, lng, kakao_place_id, last_seen_at)
VALUES (%s, %s, %s, %s, %s, %s, COALESCE(%s::timestamptz, now()))
ON CONFLICT (kakao_place_id) DO UPDATE SET
    restaurant_id = EXCLUDED.restaurant_id,
    branch_name   = EXCLUDED.branch_name,
    address       = EXCLUDED.address,
    lat           = EXCLUDED.lat,
    lng           = EXCLUDED.lng,
    last_seen_at  = EXCLUDED.last_seen_at
"""


def main():
    if not SQLITE_PATH.exists():
        raise SystemExit(f"{SQLITE_PATH} 없음")

    lite = sqlite3.connect(SQLITE_PATH)
    rows = lite.execute("""
        SELECT r.name, s.branch_name, s.address, s.lat, s.lng, s.kakao_place_id, s.last_seen_at
        FROM store s JOIN restaurant r ON r.id = s.restaurant_id
        WHERE s.kakao_place_id IS NOT NULL
    """).fetchall()
    lite.close()
    print(f"SQLite store: {len(rows)}행")

    with connect() as conn:
        ids = {r["name"]: r["id"] for r in
               conn.execute("SELECT id, name FROM restaurant").fetchall()}

        params, missing = [], set()
        for name, branch, addr, lat, lng, place_id, seen in rows:
            rid = ids.get(name)
            if rid is None:
                missing.add(name)
                continue
            params.append((rid, branch, addr, lat, lng, place_id, seen))

        if missing:
            print(f"  [skip] Postgres에 없는 브랜드: {sorted(missing)}")

        # psycopg 3.1+ executemany는 내부적으로 파이프라인을 써서 한 번에 보낸다.
        # (행별 왕복이면 Neon 지연 때문에 4천 행에 20분+ 걸린다)
        conn.cursor().executemany(UPSERT, params)

        total = conn.execute("SELECT count(*) AS n FROM store").fetchone()["n"]

    print(f"적재 {len(params)}행 -> store 총 {total}행")


if __name__ == "__main__":
    main()
