# Dining Maps — 프로젝트 컨텍스트 (AI 질의용 요약)

> 다른 AI 모델에게 이 프로젝트에 대해 질문할 때 통째로 붙여넣기 위한 문서입니다.
> 프로젝트 목적·구조·설계 결정과 그 이유·현재 상태·미해결 과제를 담고 있습니다.
> **API 키 등 시크릿은 이 문서에 포함하지 않았습니다.**

---

## 1. 한 줄 요약

프랜차이즈 메뉴의 영양정보를 **동일 기준으로 정규화해 비교**하고, 매장 위치를 **지도 위에서 탐색**할 수 있게 하는 웹 서비스. 데이터 엔지니어 포트폴리오 목적.

## 2. 문제 정의 (중요 — 방향이 한 번 바뀌었음)

**최초 가설 (폐기)**: "다이어트하는 사람이 외식할 때 갈 식당이 없어 불편하다"
→ 멘토 피드백: 검증되지 않은 개인적 추정에 가깝다는 지적을 받음.

**재정의한 문제 (현재)**: "외식할 때 주변 메뉴의 영양정보가 브랜드별로 흩어져 있어 **동일한 기준으로 비교하기 어렵다**"
→ 이건 추정이 아니라 실제 크롤링하며 데이터로 확인한 사실:
- 브랜드마다 공개하는 영양소 항목이 다름 (대부분 5종, 샐러디만 7종, 포케올데이는 9종)
- 수집 형식이 제각각 (JSON API / 정적 HTML / JS 렌더링 / **이미지로만 공개**)
- 세트 메뉴는 칼로리 "범위"만 제공해 비교 자체가 불가능

## 3. 기술 스택

| 영역 | 사용 기술 |
|---|---|
| 수집 | Python (urllib, BeautifulSoup, pandas) |
| 저장 | SQLite (`db/dining.db`) |
| API | FastAPI + Pydantic (포트 8000) |
| 프론트 | React + Vite (포트 5173), 카카오맵 JS SDK |
| 오케스트레이션 | Apache Airflow 3.3.0 + PostgreSQL 17 (Docker Compose, LocalExecutor) |
| 외부 API | 카카오 로컬 API(매장 위치), 카카오맵 JS SDK(지도 렌더링) |

## 4. 디렉토리 구조

```
dining_maps/
├── app/                    FastAPI 백엔드 -- 기능 하나 = 폴더 하나
│   ├── main.py             앱 조립(CORS + include_router)만
│   ├── restaurants/        브랜드 목록·메뉴·통계·등급  router.py + schemas.py
│   ├── stores/             매장 위치(거리·등급 필터)
│   ├── menus/              메뉴 탐색기(/api/menus)
│   ├── stats/              대시보드용 mart 조회
│   ├── recommend/          목표별 메뉴 추천
│   ├── new_menu/           신메뉴 피드
│   ├── grading.py          브랜드 절대/상대 등급 (restaurants·stores 공용)
│   └── db.py               PostgreSQL 커넥션
├── frontend-react/         React + Vite
│   └── src/
│       ├── features/       탭 하나 = 폴더 하나 (map, restaurants, dashboard,
│       │                   recommend, new-menu)
│       ├── components/     여러 기능이 같이 쓰는 표시 전용 조각
│       ├── api.js          API 호출 단일 진입점
│       └── constants.js    라벨·색상·정렬옵션
├── scripts/               실행 스크립트 -- 성격별로 폴더 하나
│   ├── crawl/             브랜드 메뉴 크롤러. crawl_common.py가 공용 fetch·파서
│   ├── pipeline/          적재→검증→채점→mart. Airflow DAG가 부르는 것들
│   ├── survey/            브랜드 확장 조사·페이지 구조 파악(수동 도구)
│   ├── llm/               LLM 배치 (브랜드 추천 메뉴, 신메뉴 리뷰)
│   ├── analytics/         GA4 리포트·커스텀 디멘션 등록
│   ├── migrate/           SQLite→PostgreSQL 1회성 이관
│   ├── deploy/            Lambda·CloudFront 배포 셸
│   └── data_analyze/      탐색용 노트북
├── dags/                   Airflow DAG 2개
├── docker/                 Airflow docker-compose
├── data/                   CSV (브랜드별 메뉴 + 조사 대장)
├── db/schema.sql           전체 스키마
└── docs/                   설계 근거 문서들
```

## 5. 데이터 모델

```sql
restaurant(id, name)

menu_item(id, restaurant_id, name, category, price_krw, weight_g,
          allergy_info, origin_info, data_source)

-- 핵심 설계: 영양소를 컬럼이 아닌 "행"으로 저장
nutrition_fact(id, menu_item_id, nutrient_name, value, unit)

diet_score(menu_item_id, score, absolute_grade, relative_grade, percentile)

store(id, restaurant_id, branch_name, address, lat, lng,
      kakao_place_id, last_seen_at)

-- 이력·품질 (append-only)
crawl_run(id, started_at, source, status)
menu_snapshot(id, run_id, restaurant_name, menu_name, category, price_krw, weight_g)
nutrition_snapshot(id, menu_snapshot_id, nutrient_name, value, unit)
data_quality_check(id, run_id, check_name, scope, severity, detail)
menu_change_log(id, run_id, restaurant_name, menu_name, change_type,
                field_name, old_value, new_value, pct_change, verdict)
```

## 6. 핵심 설계 결정과 이유

다른 AI가 "왜 이렇게 했지?"라고 되묻지 않도록, 의사결정 배경을 정리합니다.

### (1) 영양소를 key-value 행으로 저장한 이유
브랜드마다 공개 항목이 다릅니다. 고정 컬럼(`protein_g`, `carb_g`…)으로 만들면 대부분 브랜드에서 `carb_g`가 영구 NULL이 됩니다. 그래서 `nutrition_fact(nutrient_name, value, unit)` 형태로 저장합니다.

### (2) 다이어트 등급을 "절대 + 상대" 두 개로 저장한 이유
- **절대 등급**: WHO·식약처·논문에서 인용한 고정 기준. 데이터셋이 바뀌어도 흔들리지 않음 → "근거 있는 지표"라는 주장의 근거
- **상대 등급**: 현재 카탈로그 내 백분위. **B가 가장 많도록 밴드를 설계**(A≥85, B≥35, C≥10) → 실서비스에서 대부분 매장이 B로 보이게 하려는 UX 요구

절대 기준만 쓰면 거의 전부 D가 되고(패스트푸드 특성), 상대 기준만 쓰면 근거가 약해집니다. 그래서 **점수는 절대 기준 그대로 두고 등급 밴드만 상대화**해서 둘 다 저장합니다.

### (3) 등급 산정 방식 (v3)
v1(백분위) → v2(자체 추정 절대값) → **v3(문헌 인용 절대값)** 으로 두 번 갈아엎었습니다.
- v1 폐기 사유: 백분위는 평균이 항상 50 근처로 수렴 → 5개 브랜드 전부 C로 나옴
- v2 폐기 사유: "225kcal/100g" 같은 근거 약한 자체 가정 사용

**현재 v3 기준** (모두 100kcal당으로 정규화):
| 영양소 | 근거 | 좋음 / 나쁨 |
|---|---|---|
| 단백질 | 식약처 "고단백"(25%E), 장순옥(2011) 실용권장(15%E), 이홍기 외(2004) 근손실 방지선(10%E) | ≥6.25g / <2.5g |
| 당류 | WHO 5%E / 10%E | ≤1.25g / >2.5g |
| 포화지방 | AHA·ACC 5~6%E, 한국 이상지질혈증 지침 7%E | ≤0.6g / >0.8g |
| 나트륨 | AHA 1,500mg/일, WHO 2,000mg/일 (2,000kcal 기준 환산) | ≤75mg / >100mg |

100kcal 미만 메뉴는 제외(블랙커피가 밀도 왜곡으로 A등급이 되는 문제 때문).

### (4) 100g이 아닌 100kcal 기준을 쓴 이유
필라이즈처럼 100g 기준으로 가려 했으나 **샐러디가 중량(g)을 공개하지 않습니다.** 한 브랜드라도 정규화가 불가능하면 공정 비교가 깨지므로, 모든 브랜드가 갖고 있는 칼로리 기준으로 정규화했습니다.

### (5) 품질 게이트를 크롤링과 적재 "사이"에 둔 이유
`load_data.py`가 UPSERT이므로, 파서가 조용히 깨지면 나쁜 데이터가 정상 데이터를 덮어쓰고 에러도 안 납니다. 실제로 두 번 겪었습니다(롯데리아 컬럼 밀림, 아메리카노 A등급). 게이트가 실패하면 적재가 스킵되어 **기존 정상 데이터가 살아남습니다.**

### (6) "파서 버그 vs 실제 메뉴 변경" 판정 휴리스틱
> 한 브랜드 항목의 **30% 초과가 동시에 같은 필드에서** 움직이면 파서 버그로 본다.

브랜드는 메뉴를 몇 개씩 리뉴얼하지 하룻밤에 전 메뉴 나트륨을 바꾸지 않습니다. 반대로 파서가 깨지면 그 브랜드 **모든** 항목이 같은 방식으로 틀어집니다. 실제로 단백질↔나트륨 컬럼을 일부러 뒤바꿔 테스트했더니 188건 전부 `suspected_parser_bug`로 분류되고 적재가 차단됐습니다.

### (7) Airflow를 쓰는 이유 (한 번 의심받았던 지점)
"프랜차이즈 메뉴는 거의 정적인데 Airflow가 과한 것 아니냐"는 문제 제기가 있었습니다. 타당한 지적이었고, 답은 **이력 추적을 붙여서 재크롤링에 의미를 부여한 것**입니다. 스냅샷을 쌓고 변화를 감지·판정하므로 "매달 다시 긁는" 행위에 목적이 생깁니다.

### (8) React로 분리한 이유
바닐라 JS 1,009줄이 한 파일에 있었고, **브라우저 캐시 때문에 `app.js` 수정이 반영되지 않아 `?v=3→4→5`를 수동으로 올려야 했습니다.** 이건 빌드 도구가 해시 파일명으로 자동 해결하는 문제입니다. FastAPI의 `StaticFiles` 마운트를 제거하고 Vite dev 프록시 + CORS 구성으로 분리했습니다.

## 7. API 엔드포인트

```
GET /restaurants                       브랜드 목록
GET /restaurants/{id}/menu             메뉴 + 영양정보 + 등급
GET /restaurants/{id}/stats            브랜드 평균 영양소
GET /restaurants/{id}/diet-grade       브랜드 등급 요약
GET /stores?lat=&lng=&radius_m=&grade_type=&min_grade=
                                       주변 매장 (거리순 정렬, 등급 필터)
```

## 8. 현재 데이터 규모

| 항목 | 수치 |
|---|---|
| 브랜드(채택) | 5 (맥도날드·롯데리아·맘스터치·서브웨이·샐러디) |
| 메뉴 | 316 |
| 영양정보 | 2,011 |
| 등급 산정 메뉴 | 269 |
| **매장 위치** | **4,063** (전국) |

**등급 분포**
- 절대 기준: B 8 / C 112 / D 149 ← 패스트푸드 특성상 D 편중
- 상대 기준: A 40 / B 158 / C 60 / D 11 ← 의도대로 B 최다

**매장 수**: 맘스터치 1,344 · 롯데리아 1,201 · 서브웨이 657 · 맥도날드 590 · 샐러디 271

## 9. 브랜드 확장 조사 결과

`scripts/survey/survey_brands.py` → `data/brand_survey.csv` (재실행 가능한 대장)

| 상태 | 개수 |
|---|---|
| adopted (파이프라인 포함) | 5 |
| **viable (확보 가능, 미구현)** | **10** |
| rejected (영양정보 미공개) | 5 |
| unknown (재조사 필요) | 26 |

**viable 10곳**: 버거킹·스타벅스·BHC·이디야·빽다방·커피빈·할리스·포케올데이·도미노피자·배스킨라빈스
→ 채택 시 카테고리가 버거·샐러드 2종에서 **커피·치킨·피자·디저트 포함 7종**으로 확대

**rejected 사례**: 메가커피·투썸플레이스(영양정보 미공개), 노브랜드버거(팝업이 빈 페이지), 굽네치킨·한솥도시락(가격만 있고 영양정보 없음)

## 10. 가격 데이터 — 확보 실패 (중요)

당초 **슈링크플레이션 탐지**("가격은 그대로인데 중량이 줄었다")를 기획했으나 데이터가 없어 접었습니다.

- 46개 브랜드 중 **영양정보와 가격을 함께 주는 곳은 버거킹·배스킨라빈스 2곳뿐**
- 맥도날드: API에 `price` 필드가 있으나 179개 전부 `null`, 메뉴 페이지에도 가격 없음
- 카카오 로컬 API: 메뉴·가격 필드 **없음**(직접 확인)
- 한국소비자원 참가격: 김밥·자장면 등 **일반 품목**이라 프랜차이즈 메뉴와 매칭 불가
- 배달앱: 약관상 크롤링 금지 + 배달가≠매장가

프랜차이즈가 가격을 공시하지 않는 건 구조적 이유로 보임(일반매장 vs 특수매장 가격 상이).

## 11. Airflow 구성

```
nutrition_pipeline (월 1회, 기본 일시정지)
  crawl_맥도날드 ┐
  crawl_롯데리아 ├→ snapshot_and_validate → load_data → compute_diet_score
  crawl_서브웨이 │      (품질 게이트, 실패 시 하위 스킵)
  crawl_샐러디   ┘

store_location_pipeline (주 1회, 기본 일시정지)
  fetch_store_locations_nationwide → flag_stale_stores
```

맘스터치는 영양정보가 이미지로만 공개돼 자동 크롤링 대상에서 제외(수동 관리).

**주의**: Airflow는 일시정지된 DAG를 수동 트리거해도 태스크가 큐에서 대기만 하고 실행되지 않습니다. `airflow dags unpause` 후 트리거해야 합니다.

## 12. 알려진 한계 (솔직한 것들)

1. **등급 임계값(30%, 50% 등)은 경험적 추정치** — 실제 운영 데이터로 재조정 필요
2. **나트륨 기준이 다른 지표보다 가혹하게 작동** — 5개 브랜드 전부 나트륨 평균 점수가 마이너스. 사실상 통과 불가능해서 다른 지표의 변별력을 깎아먹음
3. **이홍기 외(2004) 논문은 표본 26명(여성, 6주)** — 논문 스스로도 확정하기엔 부족하다고 명시
4. **이력이 아직 얕음** — 스냅샷을 이제 막 쌓기 시작. "1년간 나트륨 추이" 분석은 시간 필요
5. **맘스터치는 이미지 OCR 없이 수동 전사** — 버거류만 반영됨
6. **`menu_item`은 UPSERT만 하고 DELETE 안 함** — 단종 메뉴가 남아있을 수 있음
7. **매장 위치 정확도** — 카카오맵에 폐업 미삭제/중복 등록이 섞여 공식 매장 수보다 많게 집계될 수 있음
8. **세트 메뉴 전면 제외** — 칼로리 범위만 제공되어 고정 영양값이 없음
9. **A등급이 거의 없음** — 절대 기준 A는 268개 중 0~1개. "프랜차이즈에 흠잡을 데 없는 다이어트 메뉴는 사실상 없다"는 결과이기도 함

## 13. 남은 작업

1. **viable 브랜드 10곳 크롤러 구현** ← 다음 작업. 자동 프로브로만 판정된 5곳(빽다방·커피빈·할리스·도미노·배스킨라빈스)은 HTML 구조 확인 필요
2. 매장 개폐업 추세 분석 (인프라는 있음, 주간 DAG 실제 가동 필요)
3. 기획안 문서(`docs/Dining_Maps_기획안.docx`)에 데이터 표준화 규칙 반영 (멘토 요청)
4. **클라우드 배포** — 멘토가 다음 실행 목표로 지목. SQLite가 컨테이너 재배포 시 초기화되는 문제 해결 필요
5. **사용자 행동 로그 수집·집계** — KPI(참여율·필터 사용률·전환율)를 측정할 로그가 현재 없음. 멘토가 지목한 가장 자연스러운 DE 확장 방향

## 14. 관련 문서

| 파일 | 내용 |
|---|---|
| `docs/diet_score.md` | 등급 산정 근거·수식·한계 (v1→v3 변천사 포함) |
| `docs/data_quality.md` | 품질 검증 룰과 파서버그 판정 휴리스틱 |
| `docs/brand_survey.md` | 브랜드 확장 조사 방법론과 결과 |
| `docs/price_data_options.md` | 가격 데이터 확보 방안 조사 및 결론 |
| `docs/Dining_Maps_기획안.docx` | 멘토 제출용 기획안 |
| `docker/README.md` | Airflow 실행법, 2.x→3.x 차이 |

## 15. 실행 방법

```bash
# 백엔드
pip install -r requirements.txt
python -m uvicorn app.main:app --reload        # http://localhost:8000

# 프론트엔드 (별도 터미널)
cd frontend-react && npm install && npm run dev # http://localhost:5173

# Airflow (선택)
cd docker && docker compose up airflow-init && docker compose up -d
                                                # http://localhost:8080
```

환경변수: `frontend-react/.env`에 `VITE_KAKAO_JS_KEY`, `docker/.env`에 `KAKAO_REST_API_KEY`·`AIRFLOW__API_AUTH__JWT_SECRET` (모두 gitignore 처리됨).
