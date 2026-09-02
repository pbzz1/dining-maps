# dbt (dining_maps 데이터 마트)

기존 OLTP 테이블(`db/schema.sql`)을 staging → dim/fact → 기존 mart 뷰(`public.mart_*`) 순으로
변환한다. `mart_*` 3개는 이름·컬럼을 그대로 유지해 `app/stats/router.py`가 안 바뀐다.

- `models/staging/` — 소스 테이블 1:1 view (schema `stg`)
- `models/marts/` — dim/fact 스타 스키마 table (schema `mart`)
- `models/marts/rollups/` — 기존 `mart_brand_nutrition`/`mart_nutrient_trend`/`mart_data_quality`를
  대체하는 table (schema `public`, 매트뷰가 아니라 dbt가 매 실행마다 `CREATE OR REPLACE TABLE`로 재계산)

## 접속 정보 (예외)

이 프로젝트의 다른 모든 코드는 `DATABASE_URL` 하나로만 DB에 접속한다(`app/db.py`).
dbt-postgres는 discrete host/port/user/password/dbname이 필요해 `profiles.yml`이
`DBT_PG_HOST`/`DBT_PG_PORT`/`DBT_PG_USER`/`DBT_PG_PASSWORD`/`DBT_PG_DBNAME`을 따로 읽는다
(`docker/docker-compose.yaml`에서 `DATABASE_URL`과 같은 값으로 나란히 주입). 단일 DSN
관용의 유일한 예외.

## 로컬 실행

```bash
export DBT_PG_HOST=localhost DBT_PG_PORT=5432 DBT_PG_USER=dining \
       DBT_PG_PASSWORD=dining DBT_PG_DBNAME=dining_maps
cd dbt
dbt run
dbt test
dbt docs generate && dbt docs serve   # 선택: 모델 문서/계보 확인
```

Airflow에서는 `dags/nutrition_pipeline.py`/`dags/store_location_pipeline.py`의
`dbt_run`/`dbt_test` 태스크가 같은 명령을 `docker-compose.yaml`의 `DBT_PG_*` 환경변수로 실행한다.
