# Dining Maps — 데이터 엔지니어링 포트폴리오

> 프랜차이즈 영양정보를 동일 기준으로 정규화해 비교하는 웹 서비스의
> 수집 → 검증 → 적재 → 가공 → 서빙 파이프라인.
> 실서비스 배포: CloudFront + Lambda + Neon PostgreSQL (Always Free 구성)

---

## 1. 문제 정의 — 조사로 확인한 사실, 추정 아님

46개 프랜차이즈 브랜드를 직접 조사(`data/brand_survey.csv`, `docs/brand_survey.md`)해서 확인한 것:

- **공개 영양소 항목이 브랜드마다 다르다** — 대부분 5종, 샐러디 7종, 포케올데이 9종
- **공개 형식이 제각각이다** — JSON API / 정적 HTML / JS 렌더링 / 이미지로만 공개
- **세트 메뉴는 칼로리 "범위"만 공개** — 고정 영양값이 없어 비교 자체가 성립 안 됨 → 스코어링 대상에서 의도적으로 제외

이 조사 결과가 이후 모든 설계 결정(스키마, 자동화 수준, 크롤러 구조)의 근거가 됐다.

## 2. 파이프라인 아키텍처

```
[Extract]              [Validate]              [Load]         [Transform]           [Serve]
crawl_*.py        →    snapshot_and_       →   load_data.py → compute_diet_     →   FastAPI(Lambda)
브랜드별 전용 파서       validate.py                             score.py              + React + 카카오맵
4개 병렬 실행            품질 게이트 (fail-fast)                  WHO 기준 절대등급
                                                               + 카탈로그 상대등급

                       Airflow DAG(nutrition_pipeline) 오케스트레이션 — 매월 1일 03:00 KST
```

핵심 파일: [dags/nutrition_pipeline.py](../dags/nutrition_pipeline.py), [dags/store_location_pipeline.py](../dags/store_location_pipeline.py)

### 품질 게이트가 하드 블로커다

- `snapshot_and_validate`가 실패하면 Airflow default trigger rule로 **하위 태스크(load/score/mart) 전부 스킵**
- 서빙 테이블은 UPSERT 방식이라 파서가 조용히 깨지면 나쁜 데이터가 정상 데이터를 덮어쓴다 — **실제로 두 번 겪은 사고**가 이 게이트를 만든 이유
- `retries=0` — 품질 실패는 flake가 아니라 진짜 신호이므로 재시도로 거짓 통과시키지 않는다

### 파서 버그 vs 실제 메뉴 변경 판정

한 브랜드 항목의 30% 초과가 같은 필드에서 동시에 움직이면 파서 버그로 판정한다.
브랜드는 메뉴 몇 개씩 리뉴얼하지, 하룻밤에 전 메뉴 나트륨을 바꾸지 않는다.
컬럼을 일부러 뒤바꿔 테스트했을 때 188건 전부 정확히 분류됐다. (`docs/data_quality.md`)

## 3. 신뢰도별 자동화 차등 — "무조건 자동화"를 하지 않은 이유

| 그룹 | 브랜드 | 관리 방식 | 이유 |
|---|---|---|---|
| 안정 파서 4곳 | 맥도날드·롯데리아·서브웨이·샐러디 | Airflow 매월 자동 재크롤 | 공식 API/HTML, 검증된 파서 |
| VERIFIED 10곳 | 스타벅스·이디야·BHC·교촌·도미노 등 | `crawl_viable_brands.py` 온디맨드 CLI | 파서 검증은 끝났지만 무인 스케줄에 올릴 신뢰 이력 부족 |
| MANUAL-ONLY | 버거킹 | 사람이 직접 실행·확인 | WAF가 urllib/curl 차단, 실제 영양 API(BKR0347)는 브라우저로만 접근 가능 |
| 수기 관리 | 맘스터치 | `data/momstouch.csv` 직접 유지 | 영양정보를 이미지로만 공개 — 자동화하면 조용히 아무것도 안 하는 태스크가 됨 |

각 파서의 신뢰 등급은 주석이 아니라 코드(`CRAWLERS` dict)에 있어 문서와 실제가 어긋날 수 없다.

## 4. 데이터 모델링 (`db/schema.sql`)

**Key-value 영양정보** — 브랜드마다 공개 항목 수가 달라 고정 컬럼이면 대부분 브랜드에서 `carb_g`가 영구 NULL. `(menu_item_id, nutrient_name, value, unit)` 행 구조로 스키마 변경 없이 브랜드 확장.

**절대 등급 + 상대 등급 이원화** — WHO/식약처/논문 기반 고정 컷오프(근거 명확, 대신 패스트푸드는 대부분 D)와 카탈로그 내 백분위(UX 적합, 대신 근거 약함)가 상충 → 점수는 절대 기준 그대로 두고 등급 밴드만 상대화해 **둘 다 저장**.

**Append-only 이력 테이블** — `crawl_run` / `menu_snapshot` / `menu_change_log`. UPSERT 서빙 테이블은 이전 값을 잃으므로 크롤 회차마다 스냅샷을 누적 → "언제부터 나트륨이 올랐나" 같은 시계열 질문에 답 가능.

**LLM 추천 캐시** — `brand_menu_reco`. 런타임 LLM 호출 대신 배치로 미리 생성하고, LLM 응답을 실제 메뉴 목록과 대조해 **환각을 걸러낸 뒤**의 menu_item_id만 저장.

**집계 mart (materialized view)** — 대시보드가 요청마다 1.2만 행을 재집계하지 않도록 파이프라인 끝에서 REFRESH.

## 5. 인프라 의사결정

| 결정 | 이유 |
|---|---|
| SQLite → PostgreSQL(Neon) 전환 | Lambda 컨테이너는 재배포 시 파일시스템 초기화 → DB 파일 소실. 로컬도 같은 엔진으로 통일해 방언 차이 사고 방지 |
| Lambda Function URL (API Gateway 없음) | 월 100만 요청 영구 무료 범위 유지 |
| S3(비공개) + CloudFront(OAC) | CloudFront 1TB/월 영구 무료, S3 월 $0.01 미만 |
| RDS 미사용 | 무료 크레딧 종료 후 월 $13~15 — Neon 무료로 충분 |
| 리전 ap-southeast-2 고정, Neon은 싱가포르 | DB 왕복 ~90ms → 엔드포인트당 쿼리 횟수 최소화 설계 (메뉴 API의 N+1 제거) |
| GitHub Actions CI/CD | master push 시 변경된 영역(app/ vs frontend-react/)만 감지해 선택 배포 |

## 6. 데이터 규모 (2026-08 기준)

| 항목 | 수치 |
|---|---|
| 브랜드 | 16 |
| 메뉴 | 2,220 |
| 영양정보 | 12,152 행 |
| 매장 위치 | 18,321 (전국, 카카오 Local API) |
| 조사 대장 | 46개 브랜드 |

## 7. 기술 스택

| 영역 | 기술 |
|---|---|
| 오케스트레이션 | Apache Airflow 3.3 (Docker Compose) |
| 저장 | PostgreSQL 17, materialized view |
| 수집 | Python, BeautifulSoup, urllib/requests |
| API | FastAPI, Pydantic, Mangum(Lambda) |
| 프론트 | React, Vite, 카카오맵 JS SDK |
| 인프라 | AWS Lambda·S3·CloudFront·IAM, Neon, GitHub Actions |

## 8. 면접 어필 포인트

1. **"왜 안 했는지"가 문서화된 설계** — 세트 메뉴 제외, 맘스터치 미자동화, 버거킹 수동 분류. 커버리지 숫자보다 데이터 신뢰성을 우선한 판단이 코드와 문서에 남아 있다.
2. **품질 게이트가 실제로 파이프라인을 막는다** — 형식적 validate가 아니라, 실패 시 하위 전체가 스킵되는 fail-fast. 실제 사고 2회에서 나온 설계.
3. **스키마가 조사 결과를 반영한다** — "브랜드마다 공개 형식이 다르다"는 실사 결과가 key-value 모델링으로 직결.
4. **비용 제약 하의 아키텍처** — Always Free 티어 안에서 실서비스 운영, 각 선택의 비용 근거가 명시돼 있다.
5. **이력 보존과 변경 감지** — append-only 스냅샷 + 파서버그/실제변경 판정 휴리스틱(테스트로 검증).

## 9. 남은 작업

- 사용자 행동 로그 설계·수집 → KPI 집계 (현재 KPI 측정 수단 없음)
- 등급 임계값을 실제 운영 데이터로 재조정
- VERIFIED 브랜드들의 무인 스케줄 승격 (신뢰 이력 축적 후)
