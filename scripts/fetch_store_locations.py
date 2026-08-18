"""Fetch real branch locations (address + lat/lng) via the Kakao Local API
keyword search, for a given center point and radius, and upsert them into
the `store` table.

Needs a Kakao REST API key (from developers.kakao.com -> app -> REST API 키;
this is a *different* key from the JavaScript key used for map rendering).
Not run yet -- waiting on the key. Once you have it:

    KAKAO_REST_API_KEY=xxxx python scripts/fetch_store_locations.py \
        --lat 37.5665 --lng 126.9780 --radius 3000
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.db import get_connection  # noqa: E402

KAKAO_KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
MAX_RADIUS_M = 20000  # Kakao's own cap
PAGE_SIZE = 15
MAX_PAGES = 3  # Kakao keyword search caps at 45 results (3 pages x 15)


def search_brand(brand_name: str, lat: float, lng: float, radius: int, api_key: str) -> list[dict]:
    results = []
    for page in range(1, MAX_PAGES + 1):
        params = {
            "query": brand_name,
            "x": lng,
            "y": lat,
            "radius": min(radius, MAX_RADIUS_M),
            "page": page,
            "size": PAGE_SIZE,
        }
        url = f"{KAKAO_KEYWORD_URL}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"Authorization": f"KakaoAK {api_key}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        results.extend(data["documents"])
        if data["meta"]["is_end"]:
            break
        time.sleep(0.2)
    return results


def upsert_store(conn, restaurant_id: int, place: dict):
    conn.execute(
        """INSERT INTO store (restaurant_id, branch_name, address, lat, lng, kakao_place_id, last_seen_at)
           VALUES (%s, %s, %s, %s, %s, %s, now())
           ON CONFLICT (kakao_place_id) DO UPDATE SET
               branch_name=excluded.branch_name, address=excluded.address,
               lat=excluded.lat, lng=excluded.lng, last_seen_at=now()""",
        (
            restaurant_id,
            place["place_name"],
            place.get("road_address_name") or place.get("address_name"),
            float(place["y"]),
            float(place["x"]),
            place["id"],
        ),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lng", type=float, required=True)
    parser.add_argument("--radius", type=int, default=3000, help="meters, max 20000")
    args = parser.parse_args()

    api_key = os.environ.get("KAKAO_REST_API_KEY")
    if not api_key:
        raise SystemExit("Set KAKAO_REST_API_KEY env var first (developers.kakao.com REST API key)")

    conn = get_connection()
    restaurants = [(r["id"], r["name"]) for r in
                   conn.execute("SELECT id, name FROM restaurant").fetchall()]

    total = 0
    for restaurant_id, name in restaurants:
        places = search_brand(name, args.lat, args.lng, args.radius, api_key)
        for place in places:
            upsert_store(conn, restaurant_id, place)
        conn.commit()
        print(f"{name}: {len(places)} branches found")
        total += len(places)
        time.sleep(0.2)

    print(f"\nDone: {total} store locations upserted.")
    conn.close()


if __name__ == "__main__":
    main()
