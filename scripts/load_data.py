"""CSV -> SQLite loader. Re-run anytime to rebuild db/dining.db from data/*.csv."""
import csv
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = ROOT / "db" / "dining.db"
SCHEMA_PATH = ROOT / "db" / "schema.sql"

# Per-CSV column mapping. Every brand publishes a different subset of
# nutrients, so each entry lists only the columns that actually exist
# in that brand's CSV.
FILES = [
    {
        "csv": "mcdonalds.csv",
        "name_col": "menu_name",
        "category_col": "menu_group",
        "price_col": "price_krw",
        "weight_col": "weight_g",
        "allergy_col": "allergy_info",
        "data_source": "official_api",
        "nutrients": {
            "calorie_kcal": ("calorie", "kcal"),
            "protein_g": ("protein", "g"),
            "sugar_g": ("sugar", "g"),
            "saturated_fat_g": ("saturated_fat", "g"),
            "sodium_mg": ("sodium", "mg"),
            "caffeine_mg": ("caffeine", "mg"),
        },
    },
    {
        "csv": "lotteria.csv",
        "name_col": "menu_name",
        "category_col": "menu_category",
        "weight_col": "weight_g",
        "allergy_col": "allergy_info",
        "origin_col": "origin_info",
        "data_source": "official_html",
        "nutrients": {
            "calorie_kcal": ("calorie", "kcal"),
            "protein_g": ("protein", "g"),
            "sugar_g": ("sugar", "g"),
            "saturated_fat_g": ("saturated_fat", "g"),
            "sodium_mg": ("sodium", "mg"),
            "caffeine_mg": ("caffeine", "mg"),
        },
    },
    {
        "csv": "momstouch.csv",
        "name_col": "menu_name",
        "category_col": "menu_category",
        "weight_col": "weight_g",
        "data_source_col": "data_source",
        "nutrients": {
            "calorie_kcal": ("calorie", "kcal"),
            "protein_g": ("protein", "g"),
            "sugar_g": ("sugar", "g"),
            "saturated_fat_g": ("saturated_fat", "g"),
            "sodium_mg": ("sodium", "mg"),
        },
    },
    {
        "csv": "subway.csv",
        "name_col": "menu_name",
        "category_col": "menu_category",
        "weight_col": "weight_g",
        "data_source": "official_html",
        "nutrients": {
            "calorie_kcal": ("calorie", "kcal"),
            "protein_g": ("protein", "g"),
            "sugar_g": ("sugar", "g"),
            "saturated_fat_g": ("saturated_fat", "g"),
            "sodium_mg": ("sodium", "mg"),
        },
    },
    {
        "csv": "salady.csv",
        "name_col": "menu_name",
        "category_col": "menu_category",
        "data_source": "official_html",
        "nutrients": {
            "calorie_kcal": ("calorie", "kcal"),
            "carb_g": ("carb", "g"),
            "sugar_g": ("sugar", "g"),
            "protein_g": ("protein", "g"),
            "fat_g": ("fat", "g"),
            "saturated_fat_g": ("saturated_fat", "g"),
            "sodium_mg": ("sodium", "mg"),
        },
    },
]


def to_float(v):
    if v is None:
        return None
    v = v.strip()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def to_int(v):
    f = to_float(v)
    return int(f) if f is not None else None


def get_or_create_restaurant(conn, name):
    cur = conn.execute("SELECT id FROM restaurant WHERE name = ?", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur = conn.execute("INSERT INTO restaurant (name) VALUES (?)", (name,))
    return cur.lastrowid


def load_file(conn, config):
    path = DATA_DIR / config["csv"]
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        item_count = 0
        fact_count = 0
        for row in reader:
            restaurant_name = row["restaurant"]
            menu_name = row.get(config["name_col"], "").strip()
            if not menu_name:
                continue

            restaurant_id = get_or_create_restaurant(conn, restaurant_name)

            category = row.get(config.get("category_col", ""), None)
            price_krw = to_int(row.get(config.get("price_col", ""), None))
            weight_g = to_float(row.get(config.get("weight_col", ""), None))
            allergy_info = row.get(config.get("allergy_col", ""), None) or None
            origin_info = row.get(config.get("origin_col", ""), None) or None
            data_source = config.get("data_source") or row.get(config.get("data_source_col", ""), None)

            cur = conn.execute(
                """INSERT INTO menu_item
                       (restaurant_id, name, category, price_krw, weight_g, allergy_info, origin_info, data_source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(restaurant_id, name) DO UPDATE SET
                       category=excluded.category, price_krw=excluded.price_krw,
                       weight_g=excluded.weight_g, allergy_info=excluded.allergy_info,
                       origin_info=excluded.origin_info, data_source=excluded.data_source
                   """,
                (restaurant_id, menu_name, category, price_krw, weight_g, allergy_info, origin_info, data_source),
            )
            menu_item_id = cur.lastrowid
            if menu_item_id == 0:
                menu_item_id = conn.execute(
                    "SELECT id FROM menu_item WHERE restaurant_id=? AND name=?",
                    (restaurant_id, menu_name),
                ).fetchone()[0]
            item_count += 1

            for csv_col, (nutrient_name, unit) in config["nutrients"].items():
                value = to_float(row.get(csv_col))
                if value is None:
                    continue
                conn.execute(
                    """INSERT INTO nutrition_fact (menu_item_id, nutrient_name, value, unit)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT(menu_item_id, nutrient_name) DO UPDATE SET
                           value=excluded.value, unit=excluded.unit""",
                    (menu_item_id, nutrient_name, value, unit),
                )
                fact_count += 1

    print(f"{config['csv']}: {item_count} menu items, {fact_count} nutrition facts")


def main():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

    for config in FILES:
        load_file(conn, config)

    conn.commit()

    total_restaurants = conn.execute("SELECT COUNT(*) FROM restaurant").fetchone()[0]
    total_items = conn.execute("SELECT COUNT(*) FROM menu_item").fetchone()[0]
    total_facts = conn.execute("SELECT COUNT(*) FROM nutrition_fact").fetchone()[0]
    print(f"\nDone: {total_restaurants} restaurants, {total_items} menu items, {total_facts} nutrition facts")
    print(f"DB written to {DB_PATH}")

    conn.close()


if __name__ == "__main__":
    main()
