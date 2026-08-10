-- Restaurant chains (교촌치킨, 맥도날드, 롯데리아, 맘스터치, 서브웨이, 샐러디 ...)
CREATE TABLE IF NOT EXISTS restaurant (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

-- One row per menu item. Only fields that exist for (almost) every brand
-- are real columns; everything nutrition-related lives in nutrition_fact
-- because each brand publishes a different subset of nutrients.
CREATE TABLE IF NOT EXISTS menu_item (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    restaurant_id INTEGER NOT NULL REFERENCES restaurant(id),
    name          TEXT NOT NULL,
    category      TEXT,
    price_krw     INTEGER,
    weight_g      REAL,
    allergy_info  TEXT,
    origin_info   TEXT,
    data_source   TEXT,   -- official_api / official_html / image_ocr_manual_verify
    UNIQUE (restaurant_id, name)
);

-- Key-value nutrition facts. Needed because McDonald's/Lotteria/Momstouch/Subway
-- only publish calorie+protein+sugar+saturated_fat+sodium, while Salady also
-- publishes total carbs and total fat. Fixed columns would leave most brands
-- with permanently-NULL carb_g/fat_g, so nutrients are modeled as rows instead.
CREATE TABLE IF NOT EXISTS nutrition_fact (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    menu_item_id  INTEGER NOT NULL REFERENCES menu_item(id),
    nutrient_name TEXT NOT NULL,   -- calorie / protein / carb / fat / sugar / saturated_fat / sodium / caffeine
    value         REAL NOT NULL,
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
    score          REAL NOT NULL,  -- 0-100, absolute (WHO/논문 기준)
    absolute_grade TEXT NOT NULL,  -- A / B / C / D, fixed cutoffs
    relative_grade TEXT NOT NULL,  -- A / B / C / D, percentile among current catalog
    percentile     REAL NOT NULL   -- 0-100, this item's percentile rank of `score`
);

-- Physical branch locations, one row per real-world store location.
-- Populated separately from menu data via the Kakao Local API
-- (scripts/fetch_store_locations.py) since brand-level menu scraping
-- tells us nothing about where branches actually are.
-- last_seen_at is bumped on every upsert (see fetch_store_locations*.py). A
-- store whose last_seen_at falls too far behind "now" was not found in the
-- most recent re-crawl -- likely closed or renamed -- and is a candidate for
-- scripts/flag_stale_stores.py to flag rather than delete outright.
CREATE TABLE IF NOT EXISTS store (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    restaurant_id INTEGER NOT NULL REFERENCES restaurant(id),
    branch_name   TEXT NOT NULL,
    address       TEXT,
    lat           REAL NOT NULL,
    lng           REAL NOT NULL,
    kakao_place_id TEXT UNIQUE,
    last_seen_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_store_restaurant ON store(restaurant_id);

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
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    source     TEXT NOT NULL,   -- manual / airflow
    status     TEXT NOT NULL    -- passed / failed
);

-- One row per (run, menu item). Append-only; never UPDATEd.
CREATE TABLE IF NOT EXISTS menu_snapshot (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES crawl_run(id),
    restaurant_name TEXT NOT NULL,
    menu_name       TEXT NOT NULL,
    category        TEXT,
    price_krw       INTEGER,
    weight_g        REAL,
    UNIQUE (run_id, restaurant_name, menu_name)
);

-- Mirrors nutrition_fact's key-value shape so a snapshot row and a serving row
-- are directly comparable.
CREATE TABLE IF NOT EXISTS nutrition_snapshot (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    menu_snapshot_id INTEGER NOT NULL REFERENCES menu_snapshot(id),
    nutrient_name    TEXT NOT NULL,
    value            REAL NOT NULL,
    unit             TEXT NOT NULL,
    UNIQUE (menu_snapshot_id, nutrient_name)
);

-- Result of each validation rule for a run. severity='fail' blocks the load.
CREATE TABLE IF NOT EXISTS data_quality_check (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
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
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES crawl_run(id),
    restaurant_name TEXT NOT NULL,
    menu_name       TEXT NOT NULL,
    change_type     TEXT NOT NULL,   -- added / removed / changed
    field_name      TEXT,            -- calorie / sodium / price_krw / ...
    old_value       TEXT,
    new_value       TEXT,
    pct_change      REAL,
    verdict         TEXT NOT NULL    -- real_change / suspected_parser_bug
);

CREATE INDEX IF NOT EXISTS idx_menu_snapshot_run ON menu_snapshot(run_id);
CREATE INDEX IF NOT EXISTS idx_nutrition_snapshot_item ON nutrition_snapshot(menu_snapshot_id);
CREATE INDEX IF NOT EXISTS idx_change_log_run ON menu_change_log(run_id);
