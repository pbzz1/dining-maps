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
import math
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from app.db import get_connection  # noqa: E402
from fetch_store_locations import search_brand, upsert_store  # noqa: E402

# Bounding box covering mainland Korea + Jeju (excludes remote west-sea
# islands like Baengnyeongdo and Dokdo -- no franchise stores there anyway).
LAT_MIN, LAT_MAX = 33.0, 38.65
LNG_MIN, LNG_MAX = 126.0, 129.75

MAX_RADIUS_M = 20000  # Kakao's max
GRID_STEP_KM = 25  # < 20km * sqrt(2) ~= 28.3km, so circles overlap with no gaps
KM_PER_DEG_LAT = 111.0

# 카카오는 한 번의 검색에 45건(3페이지 x 15)까지만 준다. 서울처럼 밀집한 곳은
# 반경 20km 원 하나에 매장이 수백 개라 45개만 받고 나머지를 통째로 놓친다.
# 실측: 서울 내 매장 수가 브랜드 상관없이 96~189로 눌려 있었다(스타벅스 139,
# 커피빈 96 -- 실제 점포 수 차이는 몇 배).
#
# 그래서 상한에 걸린 셀만 4등분해서 재귀적으로 다시 판다. 안 걸린 셀은
# 안 쪼개므로 시골은 전과 같은 속도로 지나간다.
MIN_HALF_KM = 1.0  # 한 변 2km. 이보다 작은 셀에 매장 45개는 현실적으로 없다

# ponytail: 상한에 걸렸어도 "실제 브랜드 매장"이 이만큼 안 나오면 더 안 쪼갠다.
# 45건이 찬 이유가 매장 밀도가 아니라 퍼지 매칭 쓰레기(전기차충전소, ATM 등)일
# 때 무한정 파고드는 걸 막는 휴리스틱이다. 밀집지역에서 일부 누락이 남으면
# 이 값을 낮추거나, 카카오 category_group_code로 쓰레기를 먼저 걷어내면 된다.
SUBDIVIDE_MIN_HITS = 10


def km_per_deg_lng(lat: float) -> float:
    return KM_PER_DEG_LAT * math.cos(math.radians(lat))


def build_grid() -> list[tuple[float, float]]:
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


def crawl_cell(conn, restaurant_id: int, name: str, lat: float, lng: float,
               half_km: float, api_key: str, totals: dict, stats: dict):
    """한 변이 2*half_km인 정사각형 셀을 훑는다. 45건 상한에 걸리면 4등분 재귀."""
    # 정사각형을 덮는 원의 반지름 = 반대각선 = half*sqrt(2). 5% 여유를 준다.
    radius = min(int(half_km * 1.414 * 1.05 * 1000), MAX_RADIUS_M)
    try:
        places, truncated = search_brand(name, lat, lng, radius, api_key)
    except Exception as e:
        stats["errors"] += 1
        print(f"  [warn] {name} @ ({lat:.4f},{lng:.4f}) r={radius}: {e}")
        return
    for place in places:
        upsert_store(conn, restaurant_id, place)
    totals[name] += len(places)
    stats["calls"] += 1
    time.sleep(0.1)

    if not (truncated and len(places) >= SUBDIVIDE_MIN_HITS and half_km > MIN_HALF_KM):
        return

    stats["splits"] += 1
    h = half_km / 2
    dlat = h / KM_PER_DEG_LAT
    dlng = h / km_per_deg_lng(lat)
    for slat in (lat - dlat, lat + dlat):
        for slng in (lng - dlng, lng + dlng):
            crawl_cell(conn, restaurant_id, name, slat, slng, h, api_key, totals, stats)


def main():
    api_key = os.environ.get("KAKAO_REST_API_KEY")
    if not api_key:
        raise SystemExit("Set KAKAO_REST_API_KEY env var first (developers.kakao.com REST API key)")

    conn = get_connection()
    # --missing: 이미 매장이 있는 브랜드는 건너뛴다. 브랜드 하나당 그리드 전체를
    # 도는 데 수십 분 걸려서, 신규 브랜드만 채울 때 전체 재크롤링은 낭비다.
    missing_only = "--missing" in sys.argv
    where = ("WHERE NOT EXISTS (SELECT 1 FROM store s WHERE s.restaurant_id = restaurant.id)"
             if missing_only else "")
    restaurants = [(r["id"], r["name"]) for r in
                   conn.execute(f"SELECT id, name FROM restaurant {where}").fetchall()]
    if not restaurants:
        raise SystemExit("대상 브랜드 없음")

    grid = build_grid()
    print(f"Grid: {len(grid)} points, {len(restaurants)} brands -> up to {len(grid) * len(restaurants)} base calls")

    totals = {name: 0 for _, name in restaurants}
    stats = {"calls": 0, "splits": 0, "errors": 0}
    start = time.time()

    for i, (lat, lng) in enumerate(grid):
        for restaurant_id, name in restaurants:
            crawl_cell(conn, restaurant_id, name, lat, lng,
                       GRID_STEP_KM / 2, api_key, totals, stats)
        conn.commit()

        if (i + 1) % 20 == 0 or i == len(grid) - 1:
            elapsed = time.time() - start
            print(f"[{i + 1}/{len(grid)}] {elapsed:.0f}s, "
                  f"{stats['calls']} calls / {stats['splits']} splits, totals: {totals}")

    print()
    print(f"Done in {time.time() - start:.0f}s, {stats['calls']} calls, "
          f"{stats['splits']} splits, {stats['errors']} errors.")
    print("Raw upserts per brand (before /stores endpoint dedup accounting):", totals)

    final_counts = conn.execute(
        """SELECT r.name, COUNT(*) AS n FROM store s JOIN restaurant r ON r.id = s.restaurant_id
           GROUP BY r.name ORDER BY r.name"""
    ).fetchall()
    print("\nFinal distinct store counts in DB:")
    for name, n in [(r["name"], r["n"]) for r in final_counts]:
        print(f"  {name}: {n}")

    conn.close()


if __name__ == "__main__":
    main()
