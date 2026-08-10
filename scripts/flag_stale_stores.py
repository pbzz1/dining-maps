"""List stores not seen in the most recent re-crawl(s) -- candidates for
closed/renamed branches. Doesn't delete anything; a human (or a later,
more careful automated step) decides what to do with the list.

Store locations are refreshed by re-running fetch_store_locations_nationwide.py
(planned weekly cadence -- see docs/Dining_Maps_기획안.docx "데이터 갱신 흐름").
Each upsert bumps last_seen_at, so a row that's fallen behind --stale-days
was missing from at least that many days' worth of re-crawls.

    python scripts/flag_stale_stores.py --stale-days 14
"""
import argparse
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "db" / "dining.db"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stale-days", type=int, default=14, help="flag stores not re-seen in this many days")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        """SELECT s.id, r.name, s.branch_name, s.address, s.last_seen_at,
                  CAST(julianday('now') - julianday(s.last_seen_at) AS INTEGER) AS days_stale
           FROM store s
           JOIN restaurant r ON r.id = s.restaurant_id
           WHERE julianday('now') - julianday(s.last_seen_at) > ?
           ORDER BY days_stale DESC""",
        (args.stale_days,),
    ).fetchall()
    conn.close()

    if not rows:
        print(f"No stores stale beyond {args.stale_days} days.")
        return

    print(f"{len(rows)} store(s) not re-seen in over {args.stale_days} days (closure/rename candidates):\n")
    for store_id, restaurant, branch, address, last_seen, days_stale in rows:
        print(f"  [{days_stale}d] #{store_id} {restaurant} {branch} -- {address} (last seen {last_seen})")


if __name__ == "__main__":
    main()
