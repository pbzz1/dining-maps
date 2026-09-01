"""CSV -> PostgreSQL loader. Re-run anytime to rebuild the DB from data/*.csv."""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from app.db import apply_schema, connect  # noqa: E402
from app.menu_category import category_group  # noqa: E402

DATA_DIR = ROOT / "data"

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

# The five original brands each needed a bespoke column mapping because each
# site published a different set of fields under different names. Everything
# crawled since goes through crawl_common.write_csv, which emits one fixed
# column set -- so these share a single generated entry instead of ten
# near-identical dicts. Add a brand here after its crawler produces a CSV.
STANDARD_SCHEMA_CSVS = [
    ("burgerking.csv", "버거킹"),
    ("starbucks.csv", "스타벅스"),
    ("ediya.csv", "이디야"),
    ("bhc.csv", "BHC"),
    ("kyochon.csv", "교촌치킨"),
    ("pokeallday.csv", "포케올데이"),
    ("baskinrobbins.csv", "배스킨라빈스"),
    ("paikdabang.csv", "빽다방"),
    ("coffeebean.csv", "커피빈"),
    ("hollys.csv", "할리스"),
    ("dominos.csv", "도미노피자"),
]

FILES += [
    {
        "csv": csv_name,
        "name_col": "menu_name",
        "category_col": "menu_category",
        "weight_col": "weight_g",
        "price_col": "price_krw",
        "data_source": "official_html",
        "nutrients": {
            "calorie_kcal": ("calorie", "kcal"),
            "protein_g": ("protein", "g"),
            "sugar_g": ("sugar", "g"),
            "saturated_fat_g": ("saturated_fat", "g"),
            "sodium_mg": ("sodium", "mg"),
            "caffeine_mg": ("caffeine", "mg"),
        },
    }
    for csv_name, _brand in STANDARD_SCHEMA_CSVS
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
    row = conn.execute("SELECT id FROM restaurant WHERE name = %s", (name,)).fetchone()
    if row:
        return row["id"]
    return conn.execute(
        "INSERT INTO restaurant (name) VALUES (%s) RETURNING id", (name,)
    ).fetchone()["id"]


def load_file(conn, config):
    path = DATA_DIR / config["csv"]
    if not path.exists():
        # A registered brand whose crawler hasn't produced a CSV yet. Safe to
        # skip here rather than crash: snapshot_and_validate.py's
        # brand_has_rows check already fails the run if a brand that *used to*
        # have rows suddenly has none, so a silently-vanished CSV can't slip
        # through unnoticed.
        print(f"  [skip] {config['csv']} 없음 (크롤러 미실행)")
        return 0, 0
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
            # 크롤러가 행별로 기록해둔 기준(per_serving/per_total/per_100g). 빈 값은 NULL로
            # 넣어 "미기록 = per_serving 취급"과 "빈 문자열"이 갈리지 않게 한다.
            nutrition_basis = (row.get("nutrition_basis") or "").strip() or None

            menu_item_id = conn.execute(
                """INSERT INTO menu_item
                       (restaurant_id, name, category, category_group, price_krw, weight_g,
                        allergy_info, origin_info, data_source, nutrition_basis)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (restaurant_id, name) DO UPDATE SET
                       category=excluded.category, category_group=excluded.category_group,
                       price_krw=excluded.price_krw,
                       weight_g=excluded.weight_g, allergy_info=excluded.allergy_info,
                       origin_info=excluded.origin_info, data_source=excluded.data_source,
                       nutrition_basis=excluded.nutrition_basis
                   RETURNING id""",
                (restaurant_id, menu_name, category, category_group(category, menu_name),
                 price_krw, weight_g, allergy_info, origin_info, data_source, nutrition_basis),
            ).fetchone()["id"]
            item_count += 1

            for csv_col, (nutrient_name, unit) in config["nutrients"].items():
                value = to_float(row.get(csv_col))
                if value is None:
                    continue
                conn.execute(
                    """INSERT INTO nutrition_fact (menu_item_id, nutrient_name, value, unit)
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT (menu_item_id, nutrient_name) DO UPDATE SET
                           value=excluded.value, unit=excluded.unit""",
                    (menu_item_id, nutrient_name, value, unit),
                )
                fact_count += 1

    print(f"{config['csv']}: {item_count} menu items, {fact_count} nutrition facts")


def main():
    with connect() as conn:
        apply_schema(conn)

        # load_file issues one round trip per statement (menu_item insert +
        # one per nutrient), which is ~7 round trips per row. Against a local
        # DB that's free; against a managed Postgres with real network
        # latency (Neon etc.) it adds up to thousands of round trips and the
        # load can take tens of minutes. Pipelining batches statements onto
        # the wire without waiting for each response, cutting wall-clock time
        # by roughly the round-trip count -- harmless against a local DB too.
        with conn.pipeline():
            for config in FILES:
                load_file(conn, config)

        counts = conn.execute(
            """SELECT (SELECT COUNT(*) FROM restaurant)     AS restaurants,
                      (SELECT COUNT(*) FROM menu_item)      AS items,
                      (SELECT COUNT(*) FROM nutrition_fact) AS facts"""
        ).fetchone()

    print(f"\nDone: {counts['restaurants']} restaurants, "
          f"{counts['items']} menu items, {counts['facts']} nutrition facts")


if __name__ == "__main__":
    main()
