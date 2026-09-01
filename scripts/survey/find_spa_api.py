"""Find the JSON API behind a client-rendered menu site.

13 of the surveyed brands render their menus in the browser, so urllib gets a
markup shell with no nutrition text in it (see resurvey_unknown.py's
`js_rendered` verdict). The obvious answer is browser automation, but that's
the wrong tool for a data pipeline: it's slow, fragile, and needs a browser
running on whatever box the DAG executes on.

The better answer is that the shell has to call *something* to fill itself in.
Find that endpoint once, and the brand becomes an ordinary cheap JSON crawl
forever after -- exactly what 맥도날드 and 버거킹 already are.

This script looks for it without opening a browser, by reading the JS the page
would have executed:

  1. regex the HTML and every <script src> bundle for /api/... style paths
  2. pull Next.js `buildId` so the /_next/data/<id>/<page>.json route can be
     tried (that route returns the page props -- often the whole menu)
  3. GET each candidate and report which ones return JSON

    python scripts/survey/find_spa_api.py https://bbq.co.kr
    python scripts/survey/find_spa_api.py https://nenechicken.com --filter menu

Proven on BBQ: this is how /api/delivery/menu/category was found, which
returns the live category list as JSON. Note that finding the endpoint isn't
always the end of the job -- BBQ's menu routes are scoped to a selected
delivery store, so they answer [] until a store id is supplied. The script
reports what each endpoint actually returned so that's visible rather than
guessed at.

Nothing here bypasses access control: it reads the same public JS the browser
downloads and calls the same public endpoints the page itself calls.
"""
import argparse
import json
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "crawl"))  # crawl_common
from crawl_common import fetch  # noqa: E402

# Quoted absolute paths that look like API routes. Deliberately narrow -- a
# looser pattern drowns the output in asset paths and CSS URLs.
API_PATTERN = re.compile(r"""["'`](/(?:api|v\d|graphql)[A-Za-z0-9/_\-.]*)["'`]""")
BUNDLE_PATTERN = re.compile(r'src=["\']([^"\']+\.js[^"\']*)["\']')
BUILD_ID_PATTERN = re.compile(r'"buildId"\s*:\s*"([^"]+)"')

# Endpoints worth trying first when hunting for menu data specifically.
INTERESTING = re.compile(r"menu|product|goods|categor|nutri|item|food", re.I)

MAX_BUNDLES = 12


def collect_paths(url):
    """Scrape API-looking paths out of the page and its JS bundles."""
    html = fetch(url, timeout=20)
    origin_parts = urllib.parse.urlparse(url)
    origin = f"{origin_parts.scheme}://{origin_parts.netloc}"

    paths = set(API_PATTERN.findall(html))
    bundles = BUNDLE_PATTERN.findall(html)[:MAX_BUNDLES]
    for bundle in bundles:
        try:
            js = fetch(urllib.parse.urljoin(url, bundle), timeout=20)
        except Exception:
            continue
        paths |= set(API_PATTERN.findall(js))

    build_id = BUILD_ID_PATTERN.search(html)
    return origin, paths, len(bundles), (build_id.group(1) if build_id else None)


def try_endpoint(origin, path):
    """GET one candidate and describe what came back.

    Distinguishes JSON-with-content from JSON-that-is-empty, because an empty
    array usually means the route needs a parameter (a store id, a category)
    rather than that the route is wrong.
    """
    url = origin + path
    try:
        body = fetch(url, timeout=15, headers={"Accept": "application/json"})
    except Exception as e:
        return None, f"{type(e).__name__} {getattr(e, 'code', '')}".strip()

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return None, f"JSON 아님 ({len(body):,}B)"

    if isinstance(parsed, list):
        return parsed, (f"JSON 배열 {len(parsed)}개" if parsed
                        else "빈 배열 -- 파라미터(매장/카테고리 id) 필요할 가능성")
    if isinstance(parsed, dict):
        return parsed, f"JSON 객체 keys={list(parsed)[:6]}"
    return parsed, f"JSON {type(parsed).__name__}"


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("url", help="브랜드 홈페이지 URL")
    parser.add_argument("--filter", default=None,
                        help="이 정규식에 맞는 경로만 (기본: 메뉴/제품 관련만)")
    parser.add_argument("--all", action="store_true", help="발견한 경로 전부 출력")
    parser.add_argument("--probe", action="store_true",
                        help="후보 엔드포인트를 실제로 GET 해본다")
    parser.add_argument("--max-probe", type=int, default=8)
    args = parser.parse_args()

    origin, paths, n_bundles, build_id = collect_paths(args.url)
    print(f"{origin} -- js 번들 {n_bundles}개 스캔, API 경로 {len(paths)}개 발견")
    if build_id:
        print(f"Next.js buildId={build_id}")
        print(f"  -> 페이지 데이터: {origin}/_next/data/{build_id}/<페이지>.json 시도해볼 것")

    pattern = re.compile(args.filter, re.I) if args.filter else INTERESTING
    selected = sorted(p for p in paths if args.all or pattern.search(p))
    # Templated routes (/api/menu/{id}) can't be fetched as-is.
    concrete = [p for p in selected if not re.search(r"[{}$]", p)]

    print(f"\n관심 경로 {len(selected)}개 (그중 즉시 호출 가능 {len(concrete)}개):")
    for path in selected:
        mark = "" if path in concrete else "   [템플릿 - id 필요]"
        print(f"  {path}{mark}")

    if not args.probe:
        print("\n실제 응답을 보려면 --probe 를 붙여 실행")
        return

    print("\n--- 응답 확인 ---")
    for path in concrete[:args.max_probe]:
        _, description = try_endpoint(origin, path)
        print(f"  {path:<45} {description}")


if __name__ == "__main__":
    main()
