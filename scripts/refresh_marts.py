"""대시보드 mart 3개를 재계산한다. 파이프라인(dags/*.py) 마지막 태스크.

뷰가 없으면(새 DB) db/schema.sql의 정의로 만들어지는 게 아니라 실패한다 --
스키마 적용이 먼저다. 뷰가 수백 행 이하라 REFRESH는 즉시 끝난다.

    DATABASE_URL=postgresql://... python scripts/refresh_marts.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.db import connect  # noqa: E402

MARTS = ["mart_brand_nutrition", "mart_nutrient_trend", "mart_data_quality"]


def main():
    with connect() as conn:
        for mart in MARTS:
            conn.execute(f"REFRESH MATERIALIZED VIEW {mart}")
            n = conn.execute(f"SELECT count(*) AS n FROM {mart}").fetchone()["n"]
            print(f"{mart}: {n}행")


if __name__ == "__main__":
    main()
