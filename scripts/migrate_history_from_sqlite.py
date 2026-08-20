"""옛 SQLite(db/dining.db)의 크롤 이력 5개 테이블을 Postgres로 옮긴다.

mart_nutrient_trend(월별 영양 추이)는 nutrition_snapshot 이력이 원천인데,
Postgres 전환 때 서빙 테이블만 옮기고 append-only 이력은 SQLite에 남아 있었다.
과거 5회 크롤 이력이 통째로 사라지기 전에 한 번만 이관한다.

    DATABASE_URL=postgresql://... python scripts/migrate_history_from_sqlite.py

run_id/menu_snapshot_id 참조 관계를 보존해야 하므로 id를 그대로 넣는다
(OVERRIDING SYSTEM VALUE + 시퀀스 재설정). 대상 테이블이 비어있지 않으면
id 충돌 위험이 있어 중단한다 -- 이 스크립트는 1회용이다.
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.db import connect  # noqa: E402

SQLITE_PATH = ROOT / "db" / "dining.db"

# (테이블, 컬럼들, timestamptz로 캐스팅할 컬럼)  -- 참조되는 쪽이 먼저
TABLES = [
    ("crawl_run", ["id", "started_at", "source", "status"], {"started_at"}),
    ("menu_snapshot",
     ["id", "run_id", "restaurant_name", "menu_name", "category", "price_krw", "weight_g"], set()),
    ("nutrition_snapshot",
     ["id", "menu_snapshot_id", "nutrient_name", "value", "unit"], set()),
    ("data_quality_check",
     ["id", "run_id", "check_name", "scope", "severity", "detail"], set()),
    ("menu_change_log",
     ["id", "run_id", "restaurant_name", "menu_name", "change_type",
      "field_name", "old_value", "new_value", "pct_change", "verdict"], set()),
]


def main():
    lite = sqlite3.connect(SQLITE_PATH)

    with connect() as conn:
        for table, cols, ts_cols in TABLES:
            n = conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"]
            if n:
                raise SystemExit(f"{table}에 이미 {n}행 있음 -- 1회용 스크립트라 중단")

        for table, cols, ts_cols in TABLES:
            rows = lite.execute(f"SELECT {', '.join(cols)} FROM {table}").fetchall()
            ph = ", ".join("%s::timestamptz" if c in ts_cols else "%s" for c in cols)
            conn.cursor().executemany(
                f"INSERT INTO {table} ({', '.join(cols)}) OVERRIDING SYSTEM VALUE VALUES ({ph})",
                rows)
            # id를 직접 넣었으니 시퀀스를 max(id) 뒤로 밀어야 다음 INSERT가 안 충돌한다
            conn.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"(SELECT max(id) FROM {table}))")
            print(f"{table}: {len(rows)}행")

    lite.close()


if __name__ == "__main__":
    main()
