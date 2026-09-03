"""Store location refresh pipeline (docs/Dining_Maps_기획안.docx 10.2절 계획).

Re-scans all of South Korea via the Kakao Local API (364 grid points x 5
brands, ~7 minutes) and upserts store locations, bumping last_seen_at on
every hit. Then flags branches that fell stale (not re-seen recently) as
closure/rename candidates -- it only lists them, nothing is auto-deleted.

Scheduled weekly (paused by default -- unpause in the Airflow UI to
activate). Left paused on purpose: each run burns real Kakao API quota and
takes several minutes, so it shouldn't fire automatically during review/demo.
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

from assets import MARTS, STORE

PROJECT_DIR = "/opt/airflow/dining_maps"
PYTHON = "python"

default_args = {
    "owner": "dining-maps",
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
}

with DAG(
    dag_id="store_location_pipeline",
    description="Nationwide Kakao Local API re-crawl of store locations, then flag stale (closed/renamed) branches",
    default_args=default_args,
    schedule="0 4 * * 1",  # 04:00 KST every Monday
    start_date=datetime(2026, 1, 1),
    catchup=False,
    is_paused_upon_creation=True,
    tags=["stores", "weekly"],
) as dag:

    fetch_stores = BashOperator(
        task_id="fetch_store_locations_nationwide",
        bash_command=f"cd {PROJECT_DIR} && {PYTHON} scripts/pipeline/fetch_store_locations_nationwide.py",
        outlets=[STORE],
        execution_timeout=timedelta(minutes=20),
    )

    flag_stale = BashOperator(
        task_id="flag_stale_stores",
        bash_command=f"cd {PROJECT_DIR} && {PYTHON} scripts/pipeline/flag_stale_stores.py --stale-days 14",
    )

    # dbt/models/marts/의 dim/fact + rollups(public.mart_*)를 재계산 -- 옛 refresh_marts.py
    # (REFRESH MATERIALIZED VIEW)를 대체. 상세: dbt/README.md.
    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command=f"cd {PROJECT_DIR}/dbt && dbt run --project-dir . --profiles-dir .",
        outlets=[MARTS],
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=f"cd {PROJECT_DIR}/dbt && dbt test --project-dir . --profiles-dir .",
    )

    fetch_stores >> flag_stale >> dbt_run >> dbt_test
