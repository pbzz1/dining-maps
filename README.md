# Dining Maps

프랜차이즈 메뉴의 영양정보를 **동일한 기준으로 정규화해 비교**하고, 매장 위치를 **지도에서 탐색**할 수 있게 하는 웹 서비스.

## 해결하려는 문제

외식할 때 주변 메뉴의 영양정보가 브랜드별로 흩어져 있고 형식도 제각각이라 같은 기준으로 비교하기 어렵다. 이건 추정이 아니라 실제로 46개 브랜드를 조사하며 확인한 사실이다.

- 공개하는 영양소 항목이 다르다 — 대부분 5종, 샐러디 7종, 포케올데이 9종
- 수집 형식이 다르다 — JSON API / 정적 HTML / JS 렌더링 / **이미지로만 공개**
- 세트 메뉴는 칼로리 "범위"만 줘서 애초에 비교가 성립하지 않는다

## 구성

```
수집          →  검증          →  적재      →  가공          →  서빙
crawl_*.py      snapshot_and_    load_       compute_        FastAPI
(브랜드별)       validate.py      data.py     diet_score.py   + React
                (품질 게이트)                                  + 카카오맵
                      ↑
              Airflow DAG 2개로 오케스트레이션
```

| 영역 | 기술 |
|---|---|
| 수집·가공 | Python, BeautifulSoup, pandas |
| 저장 | PostgreSQL 17 (로컬 Docker / 배포 Neon) |
| API | FastAPI, Pydantic |
| 프론트 | React, Vite, 카카오맵 JS SDK |
| 오케스트레이션 | Airflow 3.3.0, Docker Compose |
| CI/CD | GitHub Actions (master push 시 변경된 쪽만 배포) |

## 현재 데이터

| 항목 | 수치 |
|---|---|
| 브랜드 | 16 (버거·치킨·커피·샐러드·피자·아이스크림) |
| 메뉴 | 2,220 |
| 영양정보 | 12,152 |
| 매장 위치 | **18,321** (전국) |
| 브랜드 조사 대장 | 46곳 (그중 확보 완료 16곳) |

자동화 수준은 신뢰도에 따라 다르다 — 안정 파서 4곳(맥도날드·롯데리아·서브웨이·샐러디)은 Airflow가 매월 자동 재크롤, 나머지는 `crawl_viable_brands.py`로 온디맨드 실행(버거킹은 WAF 차단으로 수동, 맘스터치는 이미지 공개라 수기 관리).

## 설계에서 신경 쓴 것

**영양소를 key-value 행으로 저장** — 브랜드마다 공개 항목이 달라서, 고정 컬럼으로 만들면 대부분 브랜드에서 `carb_g`가 영구 NULL이 된다.

**다이어트 등급을 절대·상대 이중으로 산출** — 절대 기준은 WHO·식약처·논문에서 인용한 고정값이라 근거가 명확하지만 패스트푸드 특성상 대부분 D로 몰린다. 상대 기준은 현재 카탈로그 내 백분위라 UX에 적합하지만 근거가 약하다. 그래서 **점수는 절대 기준 그대로 두고 등급 밴드만 상대화**해 둘 다 저장한다.

**적재 전 품질 게이트** — `load_data.py`는 UPSERT라서 파서가 조용히 깨지면 나쁜 데이터가 정상 데이터를 덮어쓴다(실제로 두 번 겪었다). 게이트가 실패하면 적재가 스킵돼 기존 데이터가 살아남는다.

**"파서 버그 vs 실제 메뉴 변경" 판정** — 한 브랜드 항목의 30% 초과가 동시에 같은 필드에서 움직이면 파서 버그로 본다. 브랜드는 메뉴를 몇 개씩 리뉴얼하지, 하룻밤에 전 메뉴 나트륨을 바꾸지 않는다. 실제로 컬럼을 일부러 뒤바꿔 테스트했을 때 188건 전부 정확히 분류됐다.

## 실행

```bash
# 백엔드
pip install -r requirements.txt
python -m uvicorn app.main:app --reload          # localhost:8000

# 프론트엔드
cd frontend-react && npm install && npm run dev  # localhost:5173

# Airflow (선택)
cd docker && docker compose up airflow-init && docker compose up -d   # localhost:8080
```

**환경변수** — `.env.example`을 복사해 채운다.

| 파일 | 변수 |
|---|---|
| `frontend-react/.env` | `VITE_KAKAO_JS_KEY`, `VITE_API_BASE` |
| `docker/.env` | `KAKAO_REST_API_KEY`, `AIRFLOW__API_AUTH__JWT_SECRET` |

DB는 PostgreSQL이 필요하다 — `docker compose up -d postgres-app`(localhost:5432)을 띄우고 `data/*.csv`를 `python scripts/load_data.py`로 적재하면 크롤링 없이 바로 실행해볼 수 있다. (`db/dining.db`는 SQLite 시절 산출물로 더 이상 서빙에 쓰지 않는다.)

## 배포

```
브라우저 → CloudFront(S3 정적 파일) → Lambda Function URL(FastAPI) → Neon PostgreSQL
               AWS 시드니                    AWS 시드니               싱가포르
```

| 계층 | 위치 | 비용 |
|---|---|---|
| 프론트 | S3(비공개) + CloudFront(OAC), `/brand/*/` 디렉터리 URL은 CloudFront Function이 index.html로 매핑 | CloudFront 1TB/월 영구 무료, S3 월 $0.01 미만 |
| API | Lambda + Function URL (Mangum, API Gateway 없음) | 월 100만 요청 영구 무료 |
| DB | Neon PostgreSQL | 무료 |

```bash
# API (최초 생성·재배포 동일). 출력된 Function URL을 아래 프론트 배포에 넘긴다.
DATABASE_URL=postgresql://... ALLOWED_ORIGINS=https://<cloudfront-domain> bash scripts/deploy_lambda.sh
# 프론트 (빌드 → S3 sync → 캐시 무효화)
VITE_API_BASE=https://<function-url> bash scripts/deploy_frontend.sh
```

- 리전은 `ap-southeast-2` 고정 — 계정 SCP가 이 리전만 허용한다. Neon(싱가포르)과 왕복 ~90ms라 엔드포인트 안에서 쿼리 횟수를 줄여야 한다(메뉴 API의 N+1을 이 이유로 제거).
- RDS는 쓰지 않는다. 무료 플랜 크레딧($100, 6개월)이 끝나면 db.t4g.micro 기준 월 $13~15.
- Function URL 응답 상한 6MB — 파라미터 없는 `/api/stores`(전국 18k건)는 실패하지만 프론트는 항상 반경을 넘긴다.
- 새 도메인은 카카오 개발자 콘솔 → 플랫폼 → Web 사이트 도메인에 등록해야 지도가 뜬다.
- 로컬 `vite build`는 Node 24 + rolldown 조합에서 크래시해 스크립트가 `npx node@22`로 빌드한다.

## 문서

| 문서 | 내용 |
|---|---|
| [PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md) | 전체 맥락 요약 (설계 결정과 그 이유) |
| [diet_score.md](docs/diet_score.md) | 등급 산정 근거·수식·한계 (v1→v3 변천사) |
| [data_quality.md](docs/data_quality.md) | 품질 검증 룰과 파서버그 판정 휴리스틱 |
| [brand_survey.md](docs/brand_survey.md) | 브랜드 확장 조사 방법론과 결과 |
| [price_data_options.md](docs/price_data_options.md) | 가격 데이터 확보 방안 조사 및 결론 |
| [docker/README.md](docker/README.md) | Airflow 실행법, 2.x→3.x 아키텍처 차이 |

## 알려진 한계

- 등급 임계값은 경험적 추정치라 실제 운영 데이터로 재조정이 필요하다
- 나트륨 기준이 다른 지표보다 가혹해 5개 브랜드 전부 마이너스 점수를 받는다
- 세트 메뉴는 전면 제외했다 (고정 영양값이 없음)
- 매장 위치는 카카오맵 기준이라 폐업 미삭제·중복 등록이 섞여 있을 수 있다
- **KPI를 측정할 사용자 행동 로그가 아직 없다** — 다음 작업

## 다음 작업

1. ~~확보 가능한 브랜드 10곳 크롤러 구현~~ → 16개 브랜드 확보 완료
2. ~~클라우드 배포~~ → CloudFront + Lambda + Neon 으로 완료
3. 사용자 행동 로그 설계·수집 → KPI 집계
