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

# Kakao 키워드 검색은 상호를 퍼지 매칭해서 "다이소 고흥점"(맘스터치 검색),
# "파파존스 포항남구점"(도미노피자 검색), "강릉당커피콩빵"(커피빈 검색) 같은
# 남의 가게를 섞어 보낸다. 상호가 브랜드명으로 "시작"하는 것만 남긴다 --
# 단순 포함 검사로는 "투루카 ...(맥도널드 뒤)"나 "또봉이통닭 대전교촌점"이 통과한다.
#
# 공식 표기가 DB의 브랜드명과 다른 경우만 별칭을 둔다. 별칭 없이 돌리면
# 써브웨이 657곳이 통째로 걸러지므로, 브랜드 추가 시 실제 상호를 확인할 것.
BRAND_ALIASES = {
    "서브웨이": ["써브웨이"],
    "배스킨라빈스": ["베스킨라빈스"],
    "빽다방": ["뺵다방"],
}


def _norm(t: str) -> str:
    return t.replace(" ", "").lower()


def is_brand_store(brand_name: str, place_name: str) -> bool:
    prefixes = [_norm(brand_name)] + [_norm(a) for a in BRAND_ALIASES.get(brand_name, [])]
    return _norm(place_name).startswith(tuple(prefixes))


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
        results.extend(d for d in data["documents"] if is_brand_store(brand_name, d["place_name"]))
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
