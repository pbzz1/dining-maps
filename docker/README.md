# Airflow (로컬 오케스트레이션)

`scripts/`의 크롤링·적재·등급계산 스크립트를 수동 실행하는 대신 Airflow DAG로 스케줄링한다.
자세한 배경은 `docs/Dining_Maps_기획안.docx` 10장(데이터 갱신 흐름) 참고.

**버전: Airflow 3.3.0 (최신), Postgres 17.** 처음엔 별생각 없이 Airflow 2.9.3 / Postgres 16으로
설치했다가, "왜 구버전을 썼냐"는 질문을 받고서야 실제 최신 버전(Airflow 3.3.0, 2026-07-06 릴리스)을
확인하고 다시 맞췄다. 2.x → 3.x는 마이너 업그레이드가 아니라 **아키텍처가 달라지는 메이저 업그레이드**라
docker-compose를 다시 설계해야 했다 — 자세한 내용은 아래 "Airflow 3.x로 바뀐 점" 참고.

## 실행

```bash
cd docker
docker compose up airflow-init   # 최초 1회만 (DB 마이그레이션 + admin 계정 생성)
docker compose up -d
```

`http://localhost:8080` 접속 (계정: `airflow` / `airflow`).

## DAG 2개

| DAG | 내용 | 스케줄 | 기본 상태 |
|---|---|---|---|
| `nutrition_pipeline` | 4개 브랜드 크롤링(병렬) → **`snapshot_and_validate.py`(품질 게이트)** → `load_data.py` → `compute_diet_score.py` | 매월 1일 03:00 | **일시정지** |
| `store_location_pipeline` | 전국 카카오 로컬 API 재크롤링 → `flag_stale_stores.py` | 매주 월요일 04:00 | **일시정지** |

`snapshot_and_validate`는 크롤링 결과를 서빙 테이블에 넣기 **전에** 검증하는 게이트다. 브랜드가
사이트를 개편해서 파서가 조용히 깨지면 여기서 실패하고 `load_data`가 스킵되므로, 이미 들어있는
정상 데이터가 보호된다. 검증 룰과 "파서 버그 vs 실제 메뉴 변경" 판정 방식은
`docs/data_quality.md` 참고.

두 DAG 모두 기본적으로 **일시정지 상태**로 생성된다 — 특히 `store_location_pipeline`은 실행할 때마다
실제 카카오 API 쿼터를 쓰고 7분 넘게 걸려서, 리뷰/데모 중에 의도치 않게 자동 실행되지 않도록 막아둔 것.

**주의**: Airflow는 일시정지된 DAG는 수동으로 Trigger해도 태스크가 큐에서 대기만 하고 실제로 실행되지
않는다(직접 확인함 — trigger 자체는 DagRun을 만들지만 스케줄러가 paused DAG의 태스크는 큐잉하지 않는다).
실행해보려면 먼저 UI에서 토글을 켜거나 CLI로 `airflow dags unpause <dag_id>`를 실행해야 한다:

```bash
docker compose exec airflow-apiserver airflow dags unpause nutrition_pipeline
docker compose exec airflow-apiserver airflow dags trigger nutrition_pipeline
# 확인 후 다시 잠그고 싶으면:
docker compose exec airflow-apiserver airflow dags pause nutrition_pipeline
```

`nutrition_pipeline`은 이 방법으로 실제 실행해서 7개 태스크(크롤링 4개 병렬 → snapshot_and_validate
→ load_data → compute_diet_score)가 전부 success로 끝나는 것과, 호스트의 `db/dining.db`가 실제로
갱신되는 것, 그리고 웹 UI 로그인 후 실행 기록이 뜨는 것까지 확인했다.

## Airflow 3.x로 바뀐 점 (2.x 대비)

- **webserver → api-server**: 2.x의 `airflow-webserver` 서비스가 없어지고 `airflow-apiserver`(커맨드
  `api-server`)로 바뀌었다. 헬스체크 경로도 `/health` → `/api/v2/monitor/health`로 변경.
- **dag-processor가 별도 서비스로 분리**: 2.x에서는 스케줄러 프로세스 안에서 DAG 파일을 파싱했는데,
  3.x는 `airflow-dag-processor`라는 독립 서비스로 빠졌다. 컨테이너 하나가 늘어난 이유.
- **JWT 기반 내부 인증 필요**: 컴포넌트끼리(스케줄러 ↔ api-server) 통신할 때 JWT로 인증한다.
  `docker/.env`에 `AIRFLOW__API_AUTH__JWT_SECRET`을 넣어야 하고, 이게 없으면 컨테이너들이 서로
  통신을 못 해서 태스크가 영영 안 돈다.
- **AUTH_MANAGER 명시 필요**: 2.x 방식의 아이디/비밀번호 로그인(Flask-AppBuilder 기반)을 쓰려면
  `AIRFLOW__CORE__AUTH_MANAGER`를 명시적으로 FAB auth manager로 지정해야 한다 (3.x는 기본값이 다름).
- **LocalExecutor로 유지**: 공식 3.x 예제 compose는 CeleryExecutor + Redis + 별도 worker + Flower까지
  포함한 7개 서비스 구성인데, 이 프로젝트 규모(브랜드 4곳 병렬 크롤링)엔 과하다고 판단해서 2.x 때처럼
  LocalExecutor로 단순화했다 — Redis/worker/Flower 없이 postgres + api-server + scheduler +
  dag-processor + triggerer, 5개 서비스로 구성.

## 맘스터치가 `nutrition_pipeline`에 없는 이유

맘스터치는 영양정보를 이미지로만 제공해서(`docs/diet_score.md` 참고) 자동 크롤링이 불가능하다.
`data/momstouch.csv`는 수동으로 관리하는 파일로 남겨뒀다 — 자동화 태스크를 억지로 넣으면
아무 일도 안 하면서 "성공"으로 표시되는 게 더 헷갈린다고 판단했다.

## 데이터가 어디로 가는가

프로젝트 폴더 전체가 컨테이너의 `/opt/airflow/dining_maps`에 마운트된다. 즉 Airflow가 쓰는
`db/dining.db`, `data/*.csv`는 로컬에서 `python -m uvicorn app.main:app`으로 띄운 FastAPI 앱이
읽는 파일과 **완전히 동일한 파일**이다 — 별도 동기화 단계 없이, Airflow가 갱신하면 앱이 바로 그 결과를 서빙한다.

## 종료

```bash
docker compose down          # 컨테이너만 정지 (데이터는 보존)
docker compose down -v       # + Airflow 메타데이터 볼륨까지 삭제 (완전 초기화)
```
