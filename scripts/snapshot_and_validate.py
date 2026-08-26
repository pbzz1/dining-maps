"""Snapshot the freshly-crawled CSVs, validate them, and diff against the
previous crawl -- run this BETWEEN crawling and loading.

Why this exists: load_data.py UPSERTs into menu_item/nutrition_fact, so a
broken crawler silently overwrites good data with bad and the old values are
gone. This script keeps an append-only record of what each crawl saw, refuses
to let obviously-broken data through, and classifies whatever changed as a
real menu change or a suspected parser bug.

Exit code 1 on any 'fail'-severity check, so the Airflow task fails and the
downstream load is skipped. See docs/data_quality.md for the rules.

    python scripts/snapshot_and_validate.py [--source airflow]
"""
import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from app.db import apply_schema, get_connection  # noqa: E402
from load_data import FILES, to_float, to_int  # noqa: E402  (per-brand column mapping)

DATA_DIR = ROOT / "data"

# --- validation thresholds (see docs/data_quality.md for how these were picked) ---
ROW_DROP_FAIL_PCT = 0.50   # brand lost >50% of its items vs last run -> almost certainly broken
ROW_DROP_WARN_PCT = 0.20   # >20% -> worth a look, but let it through
COVERAGE_FAIL_PCT = 0.50   # a nutrient that used to be near-universal now missing for >50% of items
COVERAGE_WAS_COMMON = 0.80 # ...where "used to be near-universal" means >=80% coverage last run

# Physically implausible values -- these mean a parse error, not a real product.
VALUE_LIMITS = {
    "calorie": (0, 5000),      # kcal
    "protein": (0, 300),       # g
    "sugar": (0, 300),         # g
    "saturated_fat": (0, 300), # g
    "sodium": (0, 20000),      # mg
    "carb": (0, 500),          # g
    "fat": (0, 400),           # g
    "caffeine": (0, 1000),     # mg
}

# If more than this share of a brand's items move the SAME field in one run,
# that's a structural problem (column shifted, units changed, page redesigned),
# not a menu reformulation -- real menu changes hit a handful of items.
STRUCTURAL_CHANGE_PCT = 0.30
STRUCTURAL_MIN_ITEMS = 5   # ...but only apply that rule once there are enough items to be meaningful

COMPARED_FIELDS = ["price_krw", "weight_g"]  # menu-level numeric fields worth diffing


def read_csv_records(config):
    """Yield normalized records from one brand's CSV, using the same column
    mapping load_data.py uses so the snapshot matches what will be loaded."""
    path = DATA_DIR / config["csv"]
    if not path.exists():
        return
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            name = (row.get(config["name_col"]) or "").strip()
            if not name:
                continue
            nutrients = {}
            for csv_col, (nutrient_name, unit) in config["nutrients"].items():
                value = to_float(row.get(csv_col))
                if value is not None:
                    nutrients[nutrient_name] = (value, unit)
            yield {
                "restaurant": row["restaurant"],
                "menu_name": name,
                "category": row.get(config.get("category_col", "")) or None,
                "price_krw": to_int(row.get(config.get("price_col", ""))),
                "weight_g": to_float(row.get(config.get("weight_col", ""))),
                "nutrients": nutrients,
            }


def load_snapshot(conn, run_id):
    """Read a stored snapshot back into the same shape read_csv_records yields."""
    items = {}
    rows = conn.execute(
        """SELECT id, restaurant_name, menu_name, category, price_krw, weight_g
           FROM menu_snapshot WHERE run_id = %s""",
        (run_id,),
    ).fetchall()
    by_snapshot_id = {}
    for r in rows:
        sid, restaurant, name = r["id"], r["restaurant_name"], r["menu_name"]
        category, price, weight = r["category"], r["price_krw"], r["weight_g"]
        rec = {
            "restaurant": restaurant,
            "menu_name": name,
            "category": category,
            "price_krw": price,
            "weight_g": weight,
            "nutrients": {},
        }
        items[(restaurant, name)] = rec
        by_snapshot_id[sid] = rec

    for r in conn.execute(
        """SELECT ns.menu_snapshot_id, ns.nutrient_name, ns.value, ns.unit
           FROM nutrition_snapshot ns
           JOIN menu_snapshot ms ON ms.id = ns.menu_snapshot_id
           WHERE ms.run_id = %s""",
        (run_id,),
    ).fetchall():
        by_snapshot_id[r["menu_snapshot_id"]]["nutrients"][r["nutrient_name"]] = (r["value"], r["unit"])

    return items


def write_snapshot(conn, run_id, records):
    for rec in records.values():
        snapshot_id = conn.execute(
            """INSERT INTO menu_snapshot
                   (run_id, restaurant_name, menu_name, category, price_krw, weight_g)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
            (run_id, rec["restaurant"], rec["menu_name"], rec["category"],
             rec["price_krw"], rec["weight_g"]),
        ).fetchone()["id"]
        for nutrient, (value, unit) in rec["nutrients"].items():
            conn.execute(
                """INSERT INTO nutrition_snapshot
                       (menu_snapshot_id, nutrient_name, value, unit)
                   VALUES (%s, %s, %s, %s)""",
                (snapshot_id, nutrient, value, unit),
            )


def record_check(conn, run_id, name, scope, severity, detail):
    conn.execute(
        """INSERT INTO data_quality_check (run_id, check_name, scope, severity, detail)
           VALUES (%s, %s, %s, %s, %s)""",
        (run_id, name, scope, severity, detail),
    )
    return severity


def validate(conn, run_id, current, previous):
    """Run every rule, store results, and return True if nothing hard-failed."""
    severities = []
    brands = sorted({rec["restaurant"] for rec in current.values()})
    prev_brands = sorted({rec["restaurant"] for rec in previous.values()})

    # 1. Every brand that existed before must still produce rows.
    for brand in prev_brands:
        if brand not in brands:
            severities.append(record_check(
                conn, run_id, "brand_has_rows", brand, "fail",
                "brand produced 0 rows this run but had rows last run",
            ))
    for brand in brands:
        n = sum(1 for r in current.values() if r["restaurant"] == brand)
        if n == 0:
            severities.append(record_check(
                conn, run_id, "brand_has_rows", brand, "fail", "0 rows"))

    # 2. Row count stability vs previous run.
    if previous:
        for brand in brands:
            now = sum(1 for r in current.values() if r["restaurant"] == brand)
            before = sum(1 for r in previous.values() if r["restaurant"] == brand)
            if before == 0:
                continue
            drop = (before - now) / before
            detail = f"{before} -> {now} rows ({drop:+.1%})"
            if drop > ROW_DROP_FAIL_PCT:
                severities.append(record_check(conn, run_id, "row_count_stability", brand, "fail", detail))
            elif drop > ROW_DROP_WARN_PCT:
                severities.append(record_check(conn, run_id, "row_count_stability", brand, "warn", detail))
            else:
                severities.append(record_check(conn, run_id, "row_count_stability", brand, "pass", detail))

    # 3. Values physically plausible.
    for (brand, name), rec in current.items():
        for nutrient, (value, _unit) in rec["nutrients"].items():
            lo, hi = VALUE_LIMITS.get(nutrient, (None, None))
            if lo is None:
                continue
            if not (lo <= value <= hi):
                severities.append(record_check(
                    conn, run_id, "value_range", brand, "fail",
                    f"{name}: {nutrient}={value} outside [{lo}, {hi}]",
                ))

    # 4. A nutrient that was near-universal must not suddenly vanish.
    #    This is what catches a column shifting -- the field parses to nothing.
    if previous:
        for brand in brands:
            now_items = [r for r in current.values() if r["restaurant"] == brand]
            prev_items = [r for r in previous.values() if r["restaurant"] == brand]
            if not now_items or not prev_items:
                continue
            prev_nutrients = {n for r in prev_items for n in r["nutrients"]}
            for nutrient in sorted(prev_nutrients):
                prev_cov = sum(1 for r in prev_items if nutrient in r["nutrients"]) / len(prev_items)
                now_cov = sum(1 for r in now_items if nutrient in r["nutrients"]) / len(now_items)
                if prev_cov >= COVERAGE_WAS_COMMON and now_cov < COVERAGE_FAIL_PCT:
                    severities.append(record_check(
                        conn, run_id, "nutrient_coverage", brand, "fail",
                        f"{nutrient} coverage {prev_cov:.0%} -> {now_cov:.0%}",
                    ))

    return "fail" not in severities


def detect_changes(conn, run_id, current, previous):
    """Diff this run against the previous one and classify each change.

    A change is 'suspected_parser_bug' when a large share of one brand's items
    moved the same field at once -- brands reformulate a few items at a time,
    they don't shift every calorie value in one night.
    """
    if not previous:
        return []

    raw = []  # (brand, menu, change_type, field, old, new, pct)

    for key, rec in current.items():
        if key not in previous:
            raw.append((rec["restaurant"], rec["menu_name"], "added", None, None, None, None))
    for key, rec in previous.items():
        if key not in current:
            raw.append((rec["restaurant"], rec["menu_name"], "removed", None, None, None, None))

    for key, rec in current.items():
        if key not in previous:
            continue
        before = previous[key]
        brand, name = key

        for field in COMPARED_FIELDS:
            old, new = before.get(field), rec.get(field)
            if old is None or new is None or old == new:
                continue
            pct = (new - old) / old if old else None
            raw.append((brand, name, "changed", field, old, new, pct))

        for nutrient, (new_value, _unit) in rec["nutrients"].items():
            if nutrient not in before["nutrients"]:
                continue
            old_value = before["nutrients"][nutrient][0]
            if old_value == new_value:
                continue
            pct = (new_value - old_value) / old_value if old_value else None
            raw.append((brand, name, "changed", nutrient, old_value, new_value, pct))

    # Classify: count how many of each brand's items moved each field.
    brand_item_count = {}
    for rec in current.values():
        brand_item_count[rec["restaurant"]] = brand_item_count.get(rec["restaurant"], 0) + 1

    field_movers = {}  # (brand, field) -> set of menu names
    for brand, name, change_type, field, *_ in raw:
        if change_type == "changed":
            field_movers.setdefault((brand, field), set()).add(name)

    structural = set()
    for (brand, field), movers in field_movers.items():
        total = brand_item_count.get(brand, 0)
        if total >= STRUCTURAL_MIN_ITEMS and len(movers) / total > STRUCTURAL_CHANGE_PCT:
            structural.add((brand, field))

    rows = []
    for brand, name, change_type, field, old, new, pct in raw:
        verdict = "suspected_parser_bug" if (brand, field) in structural else "real_change"
        rows.append((run_id, brand, name, change_type, field,
                     None if old is None else str(old),
                     None if new is None else str(new),
                     pct, verdict))

    conn.cursor().executemany(
        """INSERT INTO menu_change_log
               (run_id, restaurant_name, menu_name, change_type, field_name,
                old_value, new_value, pct_change, verdict)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        rows,
    )
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="manual", help="manual / airflow")
    args = parser.parse_args()

    conn = get_connection()
    apply_schema(conn)

    prev_run = conn.execute(
        "SELECT id FROM crawl_run WHERE status = 'passed' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    prev_run_id = prev_run["id"] if prev_run else None
    previous = load_snapshot(conn, prev_run_id) if prev_run_id else {}

    run_id = conn.execute(
        "INSERT INTO crawl_run (started_at, source, status) VALUES (now(), %s, 'running') RETURNING id",
        (args.source,),
    ).fetchone()["id"]

    current = {}
    for config in FILES:
        for rec in read_csv_records(config):
            current[(rec["restaurant"], rec["menu_name"])] = rec

    write_snapshot(conn, run_id, current)
    print(f"run #{run_id}: snapshotted {len(current)} menu items"
          + (f" (comparing against run #{prev_run_id})" if prev_run_id else " (first run -- nothing to compare)"))

    passed = validate(conn, run_id, current, previous)
    changes = detect_changes(conn, run_id, current, previous)

    conn.execute("UPDATE crawl_run SET status = %s WHERE id = %s",
                 ("passed" if passed else "failed", run_id))
    conn.commit()

    checks = conn.execute(
        "SELECT severity, COUNT(*) AS n FROM data_quality_check WHERE run_id = %s GROUP BY severity",
        (run_id,),
    ).fetchall()
    print("quality checks:", ", ".join(f"{s}={n}" for s, n in checks) or "none")

    for r in conn.execute(
        """SELECT check_name, scope, detail FROM data_quality_check
           WHERE run_id = %s AND severity IN ('fail', 'warn')""",
        (run_id,),
    ).fetchall():
        print(f"  [{r['check_name']}] {r['scope']}: {r['detail']}")

    if changes:
        real = sum(1 for c in changes if c[-1] == "real_change")
        bug = len(changes) - real
        print(f"changes: {len(changes)} ({real} real_change, {bug} suspected_parser_bug)")
    else:
        print("changes: none")

    conn.close()

    if not passed:
        print("\nFAILED quality gate -- not safe to load into the serving tables.")
        sys.exit(1)


if __name__ == "__main__":
    main()
