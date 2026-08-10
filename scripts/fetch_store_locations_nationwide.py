"""Nationwide version of fetch_store_locations.py.

Kakao's keyword search caps at 45 results (3 pages x 15) per call no matter
how large the radius is, so a single "search all of Korea" call can't work
for any brand with more than ~45 branches. Instead this tiles all of South
Korea into a grid of overlapping 20km-radius search circles (grid spacing
25km, safely under the 20km*sqrt(2)~=28km gap-free threshold for a 20km
radius) and runs the same per-brand keyword search at every grid point.
Duplicate hits across overlapping circles are deduped by the `store` table's
UNIQUE(kakao_place_id) constraint via upsert, same as the single-point script.

    KAKAO_REST_API_KEY=xxxx python scripts/fetch_store_locations_nationwide.py
"""
import os
import sqlite3
import time
from pathlib import Path

from fetch_store_locations import search_brand, upsert_store

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "db" / "dining.db"

# Bounding box covering mainland Korea + Jeju (excludes remote west-sea
# islands like Baengnyeongdo and Dokdo -- no franchise stores there anyway).
LAT_MIN, LAT_MAX = 33.0, 38.65
LNG_MIN, LNG_MAX = 126.0, 129.75

RADIUS_M = 20000  # Kakao's max
GRID_STEP_KM = 25  # < 20km * sqrt(2) ~= 28.3km, so circles overlap with no gaps
KM_PER_DEG_LAT = 111.0


def build_grid() -> list[tuple[float, float]]:
    import math

    mean_lat_rad = math.radians((LAT_MIN + LAT_MAX) / 2)
    km_per_deg_lng = 111.0 * math.cos(mean_lat_rad)

    step_lat = GRID_STEP_KM / KM_PER_DEG_LAT
    step_lng = GRID_STEP_KM / km_per_deg_lng

    points = []
    lat = LAT_MIN
    while lat <= LAT_MAX:
        lng = LNG_MIN
        while lng <= LNG_MAX:
            points.append((round(lat, 4), round(lng, 4)))
            lng += step_lng
        lat += step_lat
    return points


def main():
    api_key = os.environ.get("KAKAO_REST_API_KEY")
    if not api_key:
        raise SystemExit("Set KAKAO_REST_API_KEY env var first (developers.kakao.com REST API key)")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    restaurants = conn.execute("SELECT id, name FROM restaurant").fetchall()

    grid = build_grid()
    print(f"Grid: {len(grid)} points, {len(restaurants)} brands -> up to {len(grid) * len(restaurants)} base calls")

    totals = {name: 0 for _, name in restaurants}
    errors = 0
    start = time.time()

    for i, (lat, lng) in enumerate(grid):
        for restaurant_id, name in restaurants:
            try:
                places = search_brand(name, lat, lng, RADIUS_M, api_key)
            except Exception as e:
                errors += 1
                print(f"  [warn] {name} @ ({lat},{lng}): {e}")
                continue
            for place in places:
                upsert_store(conn, restaurant_id, place)
            totals[name] += len(places)
            time.sleep(0.1)
        conn.commit()

        if (i + 1) % 20 == 0 or i == len(grid) - 1:
            elapsed = time.time() - start
            print(f"[{i + 1}/{len(grid)}] {elapsed:.0f}s elapsed, running totals: {totals}")

    print(f"\nDone in {time.time() - start:.0f}s, {errors} errors.")
    print("Raw upserts per brand (before /stores endpoint dedup accounting):", totals)

    final_counts = conn.execute(
        """SELECT r.name, COUNT(*) FROM store s JOIN restaurant r ON r.id = s.restaurant_id
           GROUP BY r.name ORDER BY r.name"""
    ).fetchall()
    print("\nFinal distinct store counts in DB:")
    for name, n in final_counts:
        print(f"  {name}: {n}")

    conn.close()


if __name__ == "__main__":
    main()
