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
import datetime
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
# 동의 쿠키가 없으면 유튜브가 동의/봇 확인 페이지를 줘서 게시일(publishDate)이 빠진다
# (GitHub Actions 러너에서 100% 재현). 이 쿠키를 붙이면 안정적으로 실린다.
HEADERS = {"User-Agent": UA, "Accept-Language": "ko", "Cookie": "SOCS=CAI; CONSENT=YES+cb"}


def top_video(query: str) -> tuple[str | None, str | None]:
    """검색 1위 (videoId, '3주 전' 같은 상대 게시 시각). 상대 시각은 watch 페이지가
    게시일을 안 줄 때의 폴백 -- 주 단위 오차지만 크롤 발견일보다 훨씬 낫다."""
    url = "https://www.youtube.com/results?hl=ko&search_query=" + urllib.parse.quote(query)
    try:
        html = urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=15)             .read().decode("utf-8", "replace")
    except Exception as e:
        print(f"  검색 실패({e}): {query}")
        return None, None
    # 첫 "videoId"는 대개 쇼츠(reelWatchEndpoint)라 게시 시각이 없고 임베드용으로도
    # 별로다. 일반 영상 블록(videoRenderer)의 첫 항목을 고르고, 상대 시각은 그 블록
    # 안(다음 videoRenderer 전까지)에서만 읽어 옆 영상 것과 섞이지 않게 한다.
    blocks = list(re.finditer(r'"videoRenderer":\{"videoId":"([A-Za-z0-9_-]{11})"', html))
    if not blocks:
        m = re.search(r'"videoId":"([A-Za-z0-9_-]{11})"', html)  # 쇼츠뿐이면 그거라도
        return (m.group(1) if m else None), None
    end = blocks[1].start() if len(blocks) > 1 else len(html)
    rel = re.search(r'"publishedTimeText":\{"simpleText":"([^"]+)"', html[blocks[0].end():end])
    return blocks[0].group(1), (rel.group(1) if rel else None)


REL_UNIT_DAYS = {"분": 0, "시간": 0, "일": 1, "주": 7, "개월": 30, "년": 365}


def approx_from_relative(text: str | None) -> str | None:
    """'3주 전' -> 오늘-21일. 정확한 게시일을 못 읽을 때만 쓰는 근사치."""
    m = re.match(r"(\d+)\s*(분|시간|일|주|개월|년)\s*전", text or "")
    if not m:
        return None
    days = int(m.group(1)) * REL_UNIT_DAYS[m.group(2)]
    return (datetime.date.today() - datetime.timedelta(days=days)).isoformat()


def publish_date(video_id: str) -> str | None:
    """영상 게시일(YYYY-MM-DD). 리뷰어는 출시 직후 올리므로 출시일의 며칠 오차 근사치 --
    크롤 발견일보다 훨씬 낫고, 온보딩·재크롤로 잡힌 옛 메뉴를 걸러내는 근거가 된다."""
    req = urllib.request.Request(f"https://www.youtube.com/watch?v={video_id}&hl=ko", headers=HEADERS)
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
        # 화면 기본값(브랜드당 5개)이 아니라 창 안의 후보 전부를 처리한다 -- 옛 메뉴가
        # 출시일 추정으로 빠지면 다음 후보가 올라오는데, 그때마다 하루씩 기다리지 않게.
        pending = [m for m in fetch_new_menus(conn, limit=500, per_brand=50, per_brand_rows=150)
                   if not m["youtube_video_id"] or not m["released_at"]]
        if not pending:
            print("조회할 신메뉴 없음")
            return
        ok = 0
        for m in pending:
            vid, rel = m["youtube_video_id"], None
            if not vid or not m["released_at"]:
                found_vid, rel = top_video(f"{m['restaurant_name']} {m['name']} 리뷰")
                vid = found_vid or vid  # 다시 검색했다면 일반 영상 우선(예전엔 쇼츠가 잡혔을 수 있음)
            if not vid:
                continue
            # 정확한 게시일(watch 페이지) -> 없으면 검색 결과의 상대 시각으로 근사
            date = None if m["released_at"] else (publish_date(vid) or approx_from_relative(rel))
            conn.execute("UPDATE menu_item SET youtube_video_id = %s WHERE id = %s", (vid, m["id"]))
            if date:  # press 출시일이 있으면 released_at이 이미 차 있어 아래는 no-op
                conn.execute(
                    """UPDATE menu_item SET released_at = %s::date, released_at_source = 'youtube'
                       WHERE id = %s AND released_at IS NULL""",
                    (date, m["id"]),
                )
            conn.commit()  # 메뉴 단위 커밋 -- 중간에 죽어도 완료분은 남는다
            ok += 1
            print(f"  {m['restaurant_name']} {m['name']}: {vid} {date or ''}")
            time.sleep(1)  # 저속 요청 -- 차단 예방
        print(f"{ok}/{len(pending)} 유튜브 영상 ID·출시일 캐시 완료")


if __name__ == "__main__":
    main()
