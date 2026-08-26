-- PostgreSQL 스키마.
--
-- 원래 SQLite였으나 배포 대상인 컨테이너 환경은 재배포 시 파일시스템이 초기화되어
-- db 파일이 사라진다. RDS 같은 관리형 DB가 필요해 PostgreSQL로 옮겼고, 로컬에서도
-- 같은 엔진을 써야 방언 차이로 인한 사고를 막을 수 있다.
--
-- SQLite 대비 바뀐 부분:
--   INTEGER PRIMARY KEY AUTOINCREMENT -> GENERATED ALWAYS AS IDENTITY
--   REAL                              -> DOUBLE PRECISION
--   TEXT + datetime('now')            -> TIMESTAMPTZ + now()

-- Restaurant chains (교촌치킨, 맥도날드, 롯데리아, 맘스터치, 서브웨이, 샐러디 ...)
CREATE TABLE IF NOT EXISTS restaurant (
    id   INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    name TEXT NOT NULL UNIQUE
);

-- One row per menu item. Only fields that exist for (almost) every brand
-- are real columns; everything nutrition-related lives in nutrition_fact
-- because each brand publishes a different subset of nutrients.
CREATE TABLE IF NOT EXISTS menu_item (
    id            INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    restaurant_id INTEGER NOT NULL REFERENCES restaurant(id),
    name          TEXT NOT NULL,
    category      TEXT,
    price_krw     INTEGER,
    weight_g      DOUBLE PRECISION,
    allergy_info  TEXT,
    origin_info   TEXT,
    data_source   TEXT,   -- official_api / official_html / image_ocr_manual_verify
    UNIQUE (restaurant_id, name)
);

-- What one row of nutrition_fact actually covers. Brands don't agree:
--   per_serving -- one item as sold (맥도날드 버거, 스타벅스 tall). The default.
--   per_total   -- the whole container/pizza (도미노 1.5L 병, S 사이즈 Subzza)
--   per_100g    -- BHC/교촌's published basis
-- NULL means unrecorded, treated as per_serving. Needed because a 1.5L bottle's
-- 660kcal is not comparable to a 355ml cup's, and the drink score is per-cup.
ALTER TABLE menu_item ADD COLUMN IF NOT EXISTS nutrition_basis TEXT;

-- Key-value nutrition facts. Needed because McDonald's/Lotteria/Momstouch/Subway
-- only publish calorie+protein+sugar+saturated_fat+sodium, while Salady also
-- publishes total carbs and total fat. Fixed columns would leave most brands
-- with permanently-NULL carb_g/fat_g, so nutrients are modeled as rows instead.
CREATE TABLE IF NOT EXISTS nutrition_fact (
    id            INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    menu_item_id  INTEGER NOT NULL REFERENCES menu_item(id),
    nutrient_name TEXT NOT NULL,   -- calorie / protein / carb / fat / sugar / saturated_fat / sodium / caffeine
    value         DOUBLE PRECISION NOT NULL,
    unit          TEXT NOT NULL,   -- kcal / g / mg
    UNIQUE (menu_item_id, nutrient_name)
);

CREATE INDEX IF NOT EXISTS idx_menu_item_restaurant ON menu_item(restaurant_id);
CREATE INDEX IF NOT EXISTS idx_nutrition_fact_item ON nutrition_fact(menu_item_id);
CREATE INDEX IF NOT EXISTS idx_nutrition_fact_name ON nutrition_fact(nutrient_name);

-- Diet-friendliness score per menu item. Computed offline by
-- scripts/compute_diet_score.py from nutrition_fact (see docs/diet_score.md
-- for the formula and why it's shaped this way) and rewritten each run,
-- so it's a derived cache table, not a source of truth.
--
-- Two grades are stored side by side because they answer different
-- questions and neither alone is enough (see docs/diet_score.md "절대
-- 기준 vs 상대 기준"):
--   absolute_grade: fixed WHO/논문-derived cutoffs on `score`. Doesn't
--     move as the catalog changes; this is the "we cite WHO" claim.
--   relative_grade: percentile rank of `score` among all currently-scored
--     items, bucketed A/B/C/D with B deliberately the largest band. Moves
--     every time compute_diet_score.py reruns on a changed catalog; this
--     is the "most restaurants show B" UX requirement.
CREATE TABLE IF NOT EXISTS diet_score (
    menu_item_id   INTEGER PRIMARY KEY REFERENCES menu_item(id),
    score          DOUBLE PRECISION NOT NULL,  -- 0-100, absolute (WHO/논문 기준)
    absolute_grade TEXT NOT NULL,  -- A / B / C / D, fixed cutoffs
    relative_grade TEXT NOT NULL,  -- A / B / C / D, percentile among current catalog
    percentile     DOUBLE PRECISION NOT NULL,  -- 0-100, percentile rank of `score` within the same basis
    basis          TEXT NOT NULL DEFAULT 'meal' -- 'meal' (per-100kcal v3 rules) / 'drink' (per-serving, no protein/sodium)
);
ALTER TABLE diet_score ADD COLUMN IF NOT EXISTS basis TEXT NOT NULL DEFAULT 'meal';

-- Physical branch locations, one row per real-world store location.
-- Populated separately from menu data via the Kakao Local API
-- (scripts/fetch_store_locations.py) since brand-level menu scraping
-- tells us nothing about where branches actually are.
-- last_seen_at is bumped on every upsert (see fetch_store_locations*.py). A
-- store whose last_seen_at falls too far behind "now" was not found in the
-- most recent re-crawl -- likely closed or renamed -- and is a candidate for
-- scripts/flag_stale_stores.py to flag rather than delete outright.
CREATE TABLE IF NOT EXISTS store (
    id            INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    restaurant_id INTEGER NOT NULL REFERENCES restaurant(id),
    branch_name   TEXT NOT NULL,
    address       TEXT,
    lat           DOUBLE PRECISION NOT NULL,
    lng           DOUBLE PRECISION NOT NULL,
    kakao_place_id TEXT UNIQUE,
    last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_store_restaurant ON store(restaurant_id);

-- LLM이 브랜드별로 미리 뽑아둔 "다이어트 추천 메뉴 + 한 문장 이유"
-- (scripts/generate_menu_reco.py, 크롤/재채점 후 배치로 갱신). 지도 팝업과
-- 매장 카드가 그대로 읽는다 -- 런타임에 LLM을 호출하지 않기 위한 캐시.
-- menu_name이 아니라 menu_item_id를 저장하는 이유: 배치 스크립트가 LLM 응답을
-- 실제 메뉴 목록과 대조해 환각을 걸러낸 뒤의 결과만 들어오게 강제하고,
-- 표시용 이름·영양정보는 조인으로 얻는다.
CREATE TABLE IF NOT EXISTS brand_menu_reco (
    restaurant_id INTEGER PRIMARY KEY REFERENCES restaurant(id),
    menu_item_id  INTEGER NOT NULL REFERENCES menu_item(id),
    reason        TEXT NOT NULL,     -- 한 문장 추천 이유 (한국어)
    model         TEXT NOT NULL,     -- 생성에 쓴 모델 ID (재현/디버깅용)
    generated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- History + data quality (scripts/snapshot_and_validate.py)
--
-- menu_item/nutrition_fact are UPSERTed on every load, which means they only
-- ever hold "what the brands publish right now" -- every previous value is
-- overwritten and lost. The tables below are append-only: they keep what each
-- crawl actually saw, so we can answer "when did this change, and by how much"
-- and tell a real menu reformulation apart from a silently-broken crawler.
-- See docs/data_quality.md.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS crawl_run (
    id         INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    started_at TIMESTAMPTZ NOT NULL,
    source     TEXT NOT NULL,   -- manual / airflow
    status     TEXT NOT NULL    -- passed / failed
);

-- One row per (run, menu item). Append-only; never UPDATEd.
CREATE TABLE IF NOT EXISTS menu_snapshot (
    id              INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    run_id          INTEGER NOT NULL REFERENCES crawl_run(id),
    restaurant_name TEXT NOT NULL,
    menu_name       TEXT NOT NULL,
    category        TEXT,
    price_krw       INTEGER,
    weight_g        DOUBLE PRECISION,
    UNIQUE (run_id, restaurant_name, menu_name)
);

-- Mirrors nutrition_fact's key-value shape so a snapshot row and a serving row
-- are directly comparable.
CREATE TABLE IF NOT EXISTS nutrition_snapshot (
    id               INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    menu_snapshot_id INTEGER NOT NULL REFERENCES menu_snapshot(id),
    nutrient_name    TEXT NOT NULL,
    value            DOUBLE PRECISION NOT NULL,
    unit             TEXT NOT NULL,
    UNIQUE (menu_snapshot_id, nutrient_name)
);

-- Result of each validation rule for a run. severity='fail' blocks the load.
CREATE TABLE IF NOT EXISTS data_quality_check (
    id         INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    run_id     INTEGER NOT NULL REFERENCES crawl_run(id),
    check_name TEXT NOT NULL,
    scope      TEXT,            -- brand name, or 'all'
    severity   TEXT NOT NULL,   -- pass / warn / fail
    detail     TEXT
);

-- Diffs between this run's snapshot and the previous one.
-- verdict distinguishes a genuine menu change from a suspected parser bug --
-- the heuristic is in docs/data_quality.md.
CREATE TABLE IF NOT EXISTS menu_change_log (
    id              INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    run_id          INTEGER NOT NULL REFERENCES crawl_run(id),
    restaurant_name TEXT NOT NULL,
    menu_name       TEXT NOT NULL,
    change_type     TEXT NOT NULL,   -- added / removed / changed
    field_name      TEXT,            -- calorie / sodium / price_krw / ...
    old_value       TEXT,
    new_value       TEXT,
    pct_change      DOUBLE PRECISION,
    verdict         TEXT NOT NULL    -- real_change / suspected_parser_bug
);

CREATE INDEX IF NOT EXISTS idx_menu_snapshot_run ON menu_snapshot(run_id);
CREATE INDEX IF NOT EXISTS idx_nutrition_snapshot_item ON nutrition_snapshot(menu_snapshot_id);
CREATE INDEX IF NOT EXISTS idx_change_log_run ON menu_change_log(run_id);

-- ---------------------------------------------------------------------------
-- 대시보드용 mart (scripts/refresh_marts.py)
--
-- 데이터는 하루 한 번 파이프라인이 돌 때만 바뀌는데 대시보드는 요청마다
-- 열린다. 요청마다 nutrition_fact 1.2만 행을 집계할 이유가 없어 결과를
-- 머티리얼라이즈드 뷰로 저장해두고, 파이프라인 끝에서 REFRESH 한다.
-- 뷰가 수백 행 이하라 REFRESH는 즉시 끝난다 (CONCURRENTLY 불필요).
-- ---------------------------------------------------------------------------

-- 브랜드별 요약: 메뉴/매장 수, 평균 점수, 등급 분포, 주요 영양소 평균.
-- avg가 조인 곱으로 왜곡되지 않도록 영양소/등급을 각자 집계한 뒤 붙인다.
CREATE MATERIALIZED VIEW IF NOT EXISTS mart_brand_nutrition AS
WITH nut AS (
    SELECT mi.restaurant_id, nf.nutrient_name, avg(nf.value) AS avg_value
    FROM nutrition_fact nf
    JOIN menu_item mi ON mi.id = nf.menu_item_id
    GROUP BY 1, 2
), grades AS (
    SELECT mi.restaurant_id,
           count(*)                                         AS scored_count,
           avg(ds.score)                                    AS avg_score,
           count(*) FILTER (WHERE ds.absolute_grade = 'A')  AS grade_a,
           count(*) FILTER (WHERE ds.absolute_grade = 'B')  AS grade_b,
           count(*) FILTER (WHERE ds.absolute_grade = 'C')  AS grade_c,
           count(*) FILTER (WHERE ds.absolute_grade = 'D')  AS grade_d
    FROM diet_score ds
    JOIN menu_item mi ON mi.id = ds.menu_item_id
    GROUP BY 1
)
SELECT r.id   AS restaurant_id,
       r.name AS restaurant_name,
       (SELECT count(*) FROM menu_item mi WHERE mi.restaurant_id = r.id) AS menu_count,
       (SELECT count(*) FROM store s WHERE s.restaurant_id = r.id)       AS store_count,
       COALESCE(g.scored_count, 0)         AS scored_count,
       round(g.avg_score::numeric, 1)      AS avg_score,
       COALESCE(g.grade_a, 0) AS grade_a,
       COALESCE(g.grade_b, 0) AS grade_b,
       COALESCE(g.grade_c, 0) AS grade_c,
       COALESCE(g.grade_d, 0) AS grade_d,
       round(MAX(n.avg_value) FILTER (WHERE n.nutrient_name = 'calorie')::numeric, 0) AS avg_calorie_kcal,
       round(MAX(n.avg_value) FILTER (WHERE n.nutrient_name = 'sodium')::numeric, 0)  AS avg_sodium_mg,
       round(MAX(n.avg_value) FILTER (WHERE n.nutrient_name = 'sugar')::numeric, 1)   AS avg_sugar_g,
       round(MAX(n.avg_value) FILTER (WHERE n.nutrient_name = 'protein')::numeric, 1) AS avg_protein_g
FROM restaurant r
LEFT JOIN grades g ON g.restaurant_id = r.id
LEFT JOIN nut n    ON n.restaurant_id = r.id
GROUP BY r.id, r.name, g.scored_count, g.avg_score,
         g.grade_a, g.grade_b, g.grade_c, g.grade_d;

-- 크롤 회차별 브랜드 x 영양소 평균. append-only 스냅샷이 원천이라
-- "언제부터 나트륨이 올랐나"를 답할 수 있는 유일한 테이블이다.
CREATE MATERIALIZED VIEW IF NOT EXISTS mart_nutrient_trend AS
SELECT cr.id         AS run_id,
       cr.started_at,
       ms.restaurant_name,
       ns.nutrient_name,
       ns.unit,
       round(avg(ns.value)::numeric, 1) AS avg_value,
       count(*)                         AS item_count
FROM crawl_run cr
JOIN menu_snapshot ms      ON ms.run_id = cr.id
JOIN nutrition_snapshot ns ON ns.menu_snapshot_id = ms.id
WHERE cr.status = 'passed'
GROUP BY 1, 2, 3, 4, 5;

-- 크롤 회차별 품질 요약: 검증 pass/warn/fail 수, 감지된 변경 건수.
-- "파이프라인이 스스로를 감시하고 있다"를 보여주는 화면의 원천.
CREATE MATERIALIZED VIEW IF NOT EXISTS mart_data_quality AS
SELECT cr.id         AS run_id,
       cr.started_at,
       cr.source,
       cr.status,
       count(dqc.id)                                    AS checks_total,
       count(*) FILTER (WHERE dqc.severity = 'pass')    AS checks_pass,
       count(*) FILTER (WHERE dqc.severity = 'warn')    AS checks_warn,
       count(*) FILTER (WHERE dqc.severity = 'fail')    AS checks_fail,
       (SELECT count(*) FROM menu_change_log m
         WHERE m.run_id = cr.id AND m.verdict = 'real_change')          AS real_changes,
       (SELECT count(*) FROM menu_change_log m
         WHERE m.run_id = cr.id AND m.verdict = 'suspected_parser_bug') AS suspected_parser_bugs
FROM crawl_run cr
LEFT JOIN data_quality_check dqc ON dqc.run_id = cr.id
GROUP BY cr.id, cr.started_at, cr.source, cr.status;
