"""Delete menu_item rows that a brand's *current* CSV no longer lists.

load_data.py only UPSERTs, so when a crawler is rewritten against a different
source (교촌치킨/포케올데이 on 2026-08-23) the old rows linger next to the new
ones. Run after load_data.py and before compute_diet_score.py:

    python scripts/prune_stale_menu_items.py kyochon pokeallday   # brand keys = CSV basenames in load_data.STANDARD_SCHEMA_CSVS
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from app.db import connect  # noqa: E402
from load_data import STANDARD_SCHEMA_CSVS  # noqa: E402


def main(keys):
    by_key = {f.removesuffix(".csv"): (f, name) for f, name in STANDARD_SCHEMA_CSVS}
    # 먼저 키를 전부 검증한다 -- DB 커넥션을 열기 전에 오타를 잡아야, 유효한 브랜드
    # 여러 개를 같이 넘겼을 때 뒤쪽 오타 하나 때문에 앞쪽 것들까지 못 지우는 사고가 안 난다.
    unknown = [k for k in keys if k not in by_key]
    if unknown:
        sys.exit(f"모르는 브랜드 키: {unknown} (유효한 키: {sorted(by_key)})")

    # 브랜드마다 독립 커밋 -- 한 브랜드 처리 중 에러(빈 CSV 등)가 나도 그 전에
    # 이미 지운 브랜드들은 롤백되지 않고 남는다.
    for key in keys:
        csv_name, restaurant = by_key[key]
        with connect() as conn:
            with open(ROOT / "data" / csv_name, encoding="utf-8-sig", newline="") as f:
                keep = [r["menu_name"].strip() for r in csv.DictReader(f)]
            if not keep:
                print(f"{csv_name}가 비어 있어 건너뜀 (전체 삭제 방지)")
                continue
            stale = conn.execute(
                """SELECT mi.id, mi.name FROM menu_item mi JOIN restaurant r ON r.id = mi.restaurant_id
                   WHERE r.name = %s AND NOT (mi.name = ANY(%s))""",
                (restaurant, keep),
            ).fetchall()
            ids = [s["id"] for s in stale]
            for table, col in (("diet_score", "menu_item_id"), ("nutrition_fact", "menu_item_id"), ("menu_item", "id")):
                conn.execute(f"DELETE FROM {table} WHERE {col} = ANY(%s)", (ids,))
            print(f"{restaurant}: pruned {len(ids)}" + (f" e.g. {[s['name'] for s in stale[:3]]}" if ids else ""))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
