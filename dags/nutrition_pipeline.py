"""Menu & nutrition refresh pipeline (docs/Dining_Maps_기획안.docx 10.1절 계획).

4 brands are crawled in parallel (McDonald's/Lotteria/Subway/Salady have
official APIs or HTML pages). The crawled CSVs are then snapshotted and
validated BEFORE anything touches the serving tables -- if a brand redesigns
its site and a parser silently breaks, snapshot_and_validate fails here and
load_data never runs, so the good data already in menu_item survives. Only
after the gate passes do we load and recompute diet scores.
See docs/data_quality.md.

맘스터치 is intentionally NOT re-crawled here: its nutrition info is only
published as an image (see docs/diet_score.md), so data/momstouch.csv stays a
manually-maintained file until that changes -- an automated task would just
silently do nothing.

Scheduled monthly (paused by default -- unpause in the Airflow UI to
activate). Menu changes happen at brand release-cycle pace, not daily.
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

PROJECT_DIR = "/opt/airflow/dining_maps"
PYTHON = "python"

default_args = {
    "owner": "dining-maps",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="nutrition_pipeline",
    description="Crawl menu/nutrition data (4 legacy + 10 expansion brands), load into DB, recompute diet scores",
    default_args=default_args,
    schedule="0 3 1 * *",  # 03:00 KST on the 1st of each month
    start_date=datetime(2026, 1, 1),
    catchup=False,
    is_paused_upon_creation=True,
    tags=["nutrition", "monthly"],
) as dag:

    crawl_tasks = [
        BashOperator(
            task_id=f"crawl_{brand}",
            bash_command=f"cd {PROJECT_DIR} && {PYTHON} scripts/crawl/crawl_{brand}.py",
        )
        for brand in ["mcdonalds", "lotteria", "subway", "salady"]
    ]

    # 2026-09 확장 브랜드 10곳 -- 파리바게뜨·메가커피·컴포즈·설빙·에그드랍·뚜레쥬르·
    # 폴바셋·미스터피자(+캡처본 파싱인 파파존스·한솥). 전부 curl 수준 요청이라 한
    # 태스크로 순차 실행한다(브랜드별 방법·검증값은 docs/crawl_handoff.md).
    # 파파존스·한솥은 저장소의 raw 캡처본을 파싱하므로 메뉴 개편 시 캡처본만 갱신하면 된다.
    crawl_tasks.append(
        BashOperator(
            task_id="crawl_new_brands",
            bash_command=f"cd {PROJECT_DIR} && {PYTHON} scripts/crawl/crawl_new_brands.py",
        )
    )

    # Quality gate: exits non-zero on any hard failure, which fails this task
    # and (by default trigger rule) skips everything downstream.
    snapshot_and_validate = BashOperator(
        task_id="snapshot_and_validate",
        bash_command=f"cd {PROJECT_DIR} && {PYTHON} scripts/pipeline/snapshot_and_validate.py --source airflow",
        retries=0,  # a failed quality gate is a real signal, not a flake -- don't retry into a false pass
    )

    load_data = BashOperator(
        task_id="load_data",
        bash_command=f"cd {PROJECT_DIR} && {PYTHON} scripts/pipeline/load_data.py",
    )

    compute_diet_score = BashOperator(
        task_id="compute_diet_score",
        bash_command=f"cd {PROJECT_DIR} && {PYTHON} scripts/pipeline/compute_diet_score.py",
    )

    refresh_marts = BashOperator(
        task_id="refresh_marts",
        bash_command=f"cd {PROJECT_DIR} && {PYTHON} scripts/pipeline/refresh_marts.py",
    )

    crawl_tasks >> snapshot_and_validate >> load_data >> compute_diet_score >> refresh_marts
