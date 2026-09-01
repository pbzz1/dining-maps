"""Delete menu_item rows that a brand's *current* CSV no longer lists.

load_data.py only UPSERTs, so when a crawler is rewritten against a different
source (교촌치킨/포케올데이 on 2026-08-23) the old rows linger next to the new
ones. Run after load_data.py and before compute_diet_score.py:

    python scripts/pipeline/prune_stale_menu_items.py kyochon pokeallday   # brand keys = CSV basenames in load_data.STANDARD_SCHEMA_CSVS
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # 같은 폴더의 스크립트를 import
from app.db import connect  # noqa: E402
from load_data import STANDARD_SCHEMA_CSVS  # noqa: E402


def main(keys):
    by_key = {f.removesuffix(".csv"): (f, name) for f, name in STANDARD_SCHEMA_CSVS}
    with connect() as conn:
        for key in keys:
            csv_name, restaurant = by_key[key]
            with open(ROOT / "data" / csv_name, encoding="utf-8-sig", newline="") as f:
                keep = [r["menu_name"].strip() for r in csv.DictReader(f)]
            if not keep:
                sys.exit(f"{csv_name} is empty -- refusing to prune everything")
            stale = conn.execute(
                """SELECT mi.id, mi.name FROM menu_item mi JOIN restaurant r ON r.id = mi.restaurant_id
                   WHERE r.name = %s AND NOT (mi.name = ANY(%s))""",
                (restaurant, keep),
            ).fetchall()
            ids = [s["id"] for s in stale]
            for table, col in (("diet_score", "menu_item_id"), ("nutrition_fact", "menu_item_id"), ("menu_item", "id")):
                conn.execute(f"DELETE FROM {table} WHERE {col} = ANY(%s)", (ids,))
            print(f"{restaurant}: pruned {len(ids)}" + (f" e.g. {[s['name'] for s in stale[:3]]}" if ids else ""))
        conn.commit()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
