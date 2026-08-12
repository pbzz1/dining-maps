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
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.db import connect  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stale-days", type=int, default=14, help="flag stores not re-seen in this many days")
    args = parser.parse_args()

    with connect() as conn:
        rows = conn.execute(
            """SELECT s.id, r.name AS restaurant, s.branch_name, s.address, s.last_seen_at,
                      EXTRACT(DAY FROM now() - s.last_seen_at)::int AS days_stale
               FROM store s
               JOIN restaurant r ON r.id = s.restaurant_id
               WHERE now() - s.last_seen_at > make_interval(days => %s)
               ORDER BY days_stale DESC""",
            (args.stale_days,),
        ).fetchall()

    if not rows:
        print(f"No stores stale beyond {args.stale_days} days.")
        return

    print(f"{len(rows)} store(s) not re-seen in over {args.stale_days} days (closure/rename candidates):\n")
    for r in rows:
        print(f"  [{r['days_stale']}d] #{r['id']} {r['restaurant']} {r['branch_name']}"
              f" -- {r['address']} (last seen {r['last_seen_at']})")


if __name__ == "__main__":
    main()
