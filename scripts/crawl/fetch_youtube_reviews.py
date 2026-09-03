"""신메뉴별 유튜브 리뷰 검색 1위 영상 ID를 menu_item.youtube_video_id에 캐시.

유튜브가 검색 결과 임베드(listType=search)를 지원 종료해서, 임베드하려면 구체적
영상 ID가 필요하다. Data API는 키 발급이 필요하니 검색 결과 HTML에서 첫
videoId를 뽑는다 -- 신메뉴는 주당 몇 건이라 요청량이 미미하고, 실패하면
조용히 건너뛴다 (프론트가 검색 링크로 대체하므로 기능이 죽지 않는다).
# ponytail: HTML 스크래핑이라 유튜브 마크업 변경에 깨질 수 있다. 깨지면
# YouTube Data API(무료 쿼터 100검색/일)로 교체.

영상 ID는 메뉴당 1회만 조회한다 -- 이미 있으면 다시 검색하지 않는다.

    DATABASE_URL=... python scripts/crawl/fetch_youtube_reviews.py
"""
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from app.db import apply_schema, connect  # noqa: E402
from app.new_menu.router import fetch_new_menus  # noqa: E402

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def top_video_id(query: str) -> str | None:
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ko"})
    try:
        html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "replace")
    except Exception as e:
        print(f"  검색 실패({e}): {query}")
        return None
    m = re.search(r'"videoId":"([A-Za-z0-9_-]{11})"', html)
    return m.group(1) if m else None


def publish_date(video_id: str) -> str | None:
    """영상 게시일(YYYY-MM-DD). 리뷰어는 출시 직후 올리므로 출시일의 며칠 오차 근사치 --
    크롤 발견일보다 훨씬 낫고, 온보딩·재크롤로 잡힌 옛 메뉴를 걸러내는 근거가 된다."""
    req = urllib.request.Request(f"https://www.youtube.com/watch?v={video_id}",
                                 headers={"User-Agent": UA, "Accept-Language": "ko"})
    try:
        html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "replace")
    except Exception as e:
        print(f"  게시일 조회 실패({e}): {video_id}")
        return None
    m = re.search(r'"publishDate":"(\d{4}-\d{2}-\d{2})', html)
    return m.group(1) if m else None


def main() -> None:
    with connect() as conn:
        apply_schema(conn)
        conn.commit()
        # 영상 ID가 없거나, 있어도 출시일이 아직 없는 메뉴 (출시일은 press가 아닐 때만 채운다)
        pending = [m for m in fetch_new_menus(conn, limit=200)
                   if not m["youtube_video_id"] or not m["released_at"]]
        if not pending:
            print("조회할 신메뉴 없음")
            return
        ok = 0
        for m in pending:
            vid = m["youtube_video_id"] or top_video_id(f"{m['restaurant_name']} {m['name']} 리뷰")
            if not vid:
                continue
            date = None if m["released_at"] else publish_date(vid)
            conn.execute(
                """UPDATE menu_item SET youtube_video_id = %s,
                       released_at = COALESCE(released_at, %s),
                       released_at_source = CASE WHEN released_at IS NULL AND %s IS NOT NULL
                                                 THEN 'youtube' ELSE released_at_source END
                   WHERE id = %s""",
                (vid, date, date, m["id"]),
            )
            conn.commit()  # 메뉴 단위 커밋 -- 중간에 죽어도 완료분은 남는다
            ok += 1
            print(f"  {m['restaurant_name']} {m['name']}: {vid} {date or ''}")
            time.sleep(1)  # 저속 요청 -- 차단 예방
        print(f"{ok}/{len(pending)} 유튜브 영상 ID·출시일 캐시 완료")


if __name__ == "__main__":
    main()
