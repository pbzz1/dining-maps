"""Re-probe the brands still marked `unknown` in data/brand_survey.csv.

26 of the 46 surveyed brands ended up `unknown` with an empty `nutrients`
column. Reading the failure notes, almost none of them are "this brand doesn't
publish nutrition data" -- they're fetch failures the first probe didn't try
hard enough to get past:

    HTTPError      13 brands  -- 403 on a desktop UA, or the path moved
    URLError        6 brands  -- www/non-www or http/https mismatch
    SSL 실패         2 brands  -- incomplete cert chain (eggdrop, bonif)
    js_rendered?    5 brands  -- fetched fine, but the menu is client-rendered

So this retries each one across the axes the first pass held fixed: both User-
Agents, both schemes, www and bare host, the m. subdomain, and a list of common
Korean franchise menu paths. Only the JS-rendered group is genuinely out of
reach for urllib -- those get flagged `js_rendered` so it's clear they need the
browser tools rather than another retry.

    python scripts/resurvey_unknown.py --dry-run     # look before writing
    python scripts/resurvey_unknown.py               # update the CSV in place
    python scripts/resurvey_unknown.py --brand KFC   # just one

Unlike survey_brands.py -- which regenerates the whole file from its own
hardcoded target list -- this edits rows in place, so hand-verified
adopted/viable/rejected rows are never touched. Rows that improve get a fresh
surveyed_at; rows that don't keep their old date, so the column keeps meaning
"when we last learned something" rather than "when a script last ran".
"""
import argparse
import concurrent.futures
import csv
import re
import sys
import urllib.parse
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from crawl_common import fetch  # noqa: E402
from survey_brands import NUTRITION_KEYWORDS, PRICE_KEYWORDS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "data" / "brand_survey.csv"
FIELDNAMES = ["brand", "category", "status", "nutrition", "nutrition_format",
              "nutrients", "price", "source", "notes", "surveyed_at"]

# Tried in order against every host variant, after the URL already on file.
# Ordered by how often Korean franchise sites actually use them.
PATH_CANDIDATES = [
    "/menu", "/menu/", "/menu/list", "/menu/menu_list", "/menu/list.asp",
    "/nutrition", "/nutrition_info", "/menu/nutrition", "/customer/nutrition",
    "/product", "/products", "/goods", "/brand/menu", "/contents/menu",
]

# Brands whose first probe fetched a full page that simply had no nutrition
# text in it -- retrying the fetch can't help, the markup is client-rendered.
# Listed explicitly so the report can say "needs a browser" instead of
# silently reporting another failure.
JS_RENDERED = {"설빙", "뚜레쥬르", "파리바게뜨", "신전떡볶이", "미스터피자", "피자헛", "KFC"}


def host_variants(url):
    """Every plausible spelling of a host, most-likely-first.

    A first-pass URLError is usually not "site is down" -- it's that the site
    redirects www -> bare (or the reverse) and urllib got the wrong one.
    """
    parsed = urllib.parse.urlparse(url if "//" in url else f"https://{url}")
    host = parsed.netloc or parsed.path.split("/")[0]
    bare = host[4:] if host.startswith("www.") else host
    hosts = [host, f"www.{bare}" if not host.startswith("www.") else bare, f"m.{bare}"]
    seen, out = set(), []
    for h in hosts:
        if h and h not in seen:
            seen.add(h)
            out.append(h)
    return out, parsed


def candidate_urls(source_url):
    """Cross host variants x schemes x paths, ordered breadth-first by path.

    Path-major ordering matters more than it looks. The failure being fixed
    here is mostly "wrong host spelling", so trying every path on www. before
    ever trying the bare host would burn the whole per-brand URL budget on the
    host we already know fails. Iterating paths on the outside means the
    recorded path gets tried on www, bare, and m. before any guessed path is
    tried anywhere.
    """
    hosts, parsed = host_variants(source_url)
    recorded = parsed.path if parsed.path not in ("", "/") else None
    # "/" must be in the list. The first version omitted it, which is how BBQ
    # -- whose recorded source is a bare domain serving a fine 77KB homepage --
    # got reported `unreachable`: every guessed path 404'd and the root was
    # never tried. The root is also what link discovery needs.
    paths = ([recorded] if recorded else []) + ["/"] + \
            [p for p in PATH_CANDIDATES if p not in (recorded, "/")]

    urls = []
    for path in paths:
        for host in hosts:
            for scheme in ("https", "http"):
                urls.append(f"{scheme}://{host}{path}")
    seen, out = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


MENU_LINK_KEYWORDS = [("영양", 5), ("nutrition", 5), ("성분", 4), ("ingredient", 4),
                      ("메뉴", 3), ("menu", 3), ("제품", 2), ("product", 2)]


def discover_menu_links(html, page_url, limit=5):
    """Rank same-host links that look like menu/nutrition pages.

    Guessing paths from PATH_CANDIDATES only finds sites that happen to use a
    conventional URL. Reading the site's own navigation finds the rest --
    that's how 본죽's real path turned out to be /brand/menu?brdCd=BF101 and
    BBQ's /categories/17, neither of which any guess list would contain.
    """
    soup = BeautifulSoup(html, "html.parser")
    host = urllib.parse.urlparse(page_url).netloc
    scored = {}
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        url = urllib.parse.urljoin(page_url, href)
        if urllib.parse.urlparse(url).netloc != host:
            continue
        hay = f"{href} {a.get_text(' ')}".lower()
        score = sum(w for kw, w in MENU_LINK_KEYWORDS if kw in hay)
        if score:
            scored[url] = max(scored.get(url, 0), score)
    return [u for u, _ in sorted(scored.items(), key=lambda kv: -kv[1])[:limit]]


def is_js_shell(html):
    """True when a page is markup with almost no text -- a client-rendered shell.

    Measured, not guessed: the SPAs confirmed by hand come in at 0.8-3% text
    (BBQ 650 chars of text in 77KB, 컴포즈커피 57 in 6.5KB), while
    server-rendered menu pages are an order of magnitude denser. 5% separates
    them with room to spare.

    This distinction is the whole point of the rewrite -- calling these
    `unreachable` implied "retry later", when the truth is "urllib will never
    work here, use browser tooling or find the JSON API behind it".
    """
    if len(html) < 2000:
        return False
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ")).strip()
    return len(text) < len(html) * 0.05


def score_page(html):
    """Count distinct nutrition signals, merging the calorie synonyms.

    Same rule survey_brands.probe_brand uses -- 열량/kcal/칼로리 all mean the
    same thing, so a page saying all three isn't three times as promising.
    """
    hits = [k for k in NUTRITION_KEYWORDS if k in html]
    merged = {"열량" if k in ("열량", "kcal", "Kcal", "칼로리") else k for k in hits}
    return len(merged), hits


def probe(brand, row, max_urls):
    """Try candidate URLs until one yields a strong nutrition signal.

    The mobile UA is a fallback, not a second pass over everything: it's only
    worth a request when desktop either errored (some sites 403 desktop UAs)
    or returned a page with no nutrition text (some sites publish nutrition on
    m. only). Trying both unconditionally would double the request count for
    no new information on the brands that already work.
    """
    state = {"best": None, "tried": 0, "errors": [], "discovered": False}

    def attempt(url):
        """Fetch one URL, update the running best, and report its score."""
        if state["tried"] >= max_urls:
            return None
        state["tried"] += 1
        try:
            html = fetch(url, timeout=10)
        except Exception as e:
            state["errors"].append((url, e))
            html = None

        mobile_used = False
        if html is None or score_page(html)[0] == 0:
            state["tried"] += 1
            try:
                m_html = fetch(url, timeout=10, mobile=True)
            except Exception as e:
                state["errors"].append((url, e))
                m_html = None
            if m_html is not None and (html is None or score_page(m_html)[0] > score_page(html)[0]):
                html, mobile_used = m_html, True

        if html is None:
            return None
        strong, hits = score_page(html)
        best = state["best"]
        if best is None or strong > best["strong"]:
            state["best"] = {"strong": strong, "url": url, "hits": hits,
                             "html": html, "mobile": mobile_used, "note": ""}
        return strong

    for url in candidate_urls(row["source"]):
        if state["tried"] >= max_urls:
            break
        strong = attempt(url)
        if strong is not None and strong >= 4:
            break

        # A page that loads but shows nothing is the interesting case: this is
        # a real site whose menu lives somewhere we haven't guessed. Follow its
        # own navigation once rather than burning the rest of the budget on
        # more guesses.
        if strong == 0 and not state["discovered"]:
            state["discovered"] = True
            for link in discover_menu_links(state["best"]["html"], state["best"]["url"]):
                if state["tried"] >= max_urls:
                    break
                link_strong = attempt(link)
                if link_strong is not None and link_strong >= 4:
                    break
    return _verdict(brand, row, state)


def _classify_errors(errors):
    """Name the actual failure mode instead of lumping everything into 'unreachable'.

    These three need completely different follow-up work, so collapsing them
    into one label made the register useless for planning: a DNS failure means
    "find the right domain" (30 seconds), a 403 means "this needs a real
    browser" (hours), and a 404 means "the path moved" (a link-discovery pass).
    """
    dns = conn_refused = forbidden = not_found = 0
    for _, e in errors:
        code = getattr(e, "code", None)
        reason = str(getattr(e, "reason", e))
        if code == 403:
            forbidden += 1
        elif code == 404:
            not_found += 1
        elif "getaddrinfo" in reason or "Name or service" in reason:
            dns += 1
        elif "10061" in reason or "refused" in reason.lower():
            conn_refused += 1

    if dns and dns >= max(conn_refused, forbidden, not_found):
        return "dns_failure", "도메인이 DNS에 없음 - 정확한 도메인 재확인 필요"
    if forbidden:
        return "blocked", "HTTP 403 - WAF가 urllib을 차단. 브라우저 도구 필요"
    if conn_refused:
        return "unreachable", "연결 거부 - 서비스 중단이거나 도메인 오류"
    if not_found:
        return "path_unknown", "호스트는 응답하나 경로 전부 404 - 메뉴 경로 재확인 필요"
    return "unreachable", "접근 실패"


def _keep_source(old_source, new_url):
    """Choose between the recorded URL and the one that actually responded.

    A probe that only reached the homepage must not overwrite a specific
    recorded path with "/". That happened on the first real run: 교촌치킨's
    `?product_id=` template and 본죽 / 본죽&비빔밥 / 본도시락's three distinct
    brand paths all collapsed to their site root, which erased the difference
    between three separate brands sharing one host.
    """
    new = urllib.parse.urlparse(new_url)
    old = urllib.parse.urlparse(old_source)
    if new.path in ("", "/") and old.path not in ("", "/"):
        return old_source
    # Same page, but the recorded URL carries a query template and the probed
    # one doesn't. 교촌치킨's `?product_id=` is the case: both point at
    # /menu/menu_view, but only the recorded form documents how to iterate
    # products, which is the entire value of the URL to whoever writes the
    # parser next.
    if new.path == old.path and old.query and not new.query:
        return old_source
    return new_url


def _merge_notes(old_notes, new_note):
    """Never drop a hand-verified note in favour of an automated one.

    `[수동확인]` notes come from a human opening the page, and they carry facts
    a keyword probe cannot rediscover -- 교촌치킨's "100g당 표기" is the
    dangerous one, because loading per-100g values as if they were per-serving
    silently corrupts every diet score for that brand.

    Written to be idempotent. Checking only whether the note *starts with*
    `[수동확인]` was not: after one merge the manual text sits at the end, so
    the very next run stopped recognising it and dropped it again. Splitting on
    the separator and keeping every manual segment survives any number of runs.
    """
    manual = [seg.strip() for seg in (old_notes or "").split(" / ")
              if "[수동확인]" in seg]
    return " / ".join([new_note] + manual) if manual else new_note


def _verdict(brand, row, state):
    """Turn the best probe result into updated CSV fields."""
    out = dict(row)
    best = state["best"]
    if best is None:
        fmt, note = _classify_errors(state["errors"])
        out["nutrition_format"] = fmt
        out["notes"] = _merge_notes(row.get("notes"), f"[재조사] {note}")
        # A newly-identified failure mode IS something learned, even though no
        # nutrition data came of it -- it changes what to do next.
        return out, fmt != "unreachable"

    html = best.get("html", "")
    hits = best.get("hits", [])
    strong = best["strong"]
    price = "Y" if any(k in html for k in PRICE_KEYWORDS) else "N"
    ua = " (모바일 UA)" if best.get("mobile") else ""
    source = _keep_source(row.get("source", ""), best["url"])

    if strong >= 4:
        out.update({
            "status": "viable", "nutrition": "Y", "nutrition_format": "server_html",
            "nutrients": ",".join(hits), "price": price, "source": source,
            "notes": _merge_notes(
                row.get("notes"),
                f"[재조사] 영양 키워드 {strong}종 검출{ua}. 크롤링 가능 - 파서 작성 필요"),
        })
        return out, True
    if strong >= 1:
        out.update({
            "status": "unknown", "nutrition": "partial", "nutrition_format": "unknown",
            "nutrients": ",".join(hits), "price": price, "source": source,
            "notes": _merge_notes(
                row.get("notes"),
                f"[재조사] 영양 키워드 일부만({strong}종) 검출{ua} - 상세페이지 확인 필요"),
        })
        return out, True

    # Reached the page but found nothing. Distinguish "client-rendered" from
    # "genuinely doesn't publish" -- these look identical in a status code but
    # mean opposite things about whether the brand is worth pursuing.
    if brand in JS_RENDERED or is_js_shell(html):
        out.update({
            "nutrition_format": "js_rendered", "source": source, "price": price,
            "notes": _merge_notes(
                row.get("notes"),
                f"[재조사] 페이지는 받았으나 영양 키워드 0종({len(html)}바이트, 텍스트 5% 미만). "
                "JS 렌더링 - urllib으로는 불가. 브라우저 도구 또는 배후 JSON API 필요"),
        })
    else:
        # Rejection is close to permanent -- rejected brands drop out of the
        # re-probe pool -- so it needs stronger evidence than "a page loaded
        # and had no nutrition words in it".
        #
        # 이삭토스트 is why. Every /menu variant 403s, but the homepage serves
        # a normal 53KB page, and the first version of this rule read that as
        # "brand publishes nothing" and rejected it. A homepage having no
        # nutrition text proves nothing at all; the menu page was never seen.
        blocked = any(getattr(e, "code", None) in (403, 406) for _, e in state["errors"])
        on_root = urllib.parse.urlparse(best["url"]).path in ("", "/")

        if blocked:
            out.update({
                "nutrition_format": "blocked", "source": source, "price": price,
                "notes": _merge_notes(
                    row.get("notes"),
                    "[재조사] 홈페이지는 열리나 메뉴 경로가 403/406 - WAF 차단. 브라우저 도구 필요"),
            })
        elif on_root:
            out.update({
                "nutrition_format": "path_unknown", "source": source, "price": price,
                "notes": _merge_notes(
                    row.get("notes"),
                    "[재조사] 홈페이지만 수신됨. 메뉴 페이지에 도달하지 못해 "
                    "영양정보 유무 판단 불가 - 메뉴 경로 재확인 필요"),
            })
        else:
            out.update({
                "status": "rejected", "nutrition": "N", "nutrition_format": "none",
                "source": source, "price": price,
                "notes": _merge_notes(
                    row.get("notes"),
                    f"[재조사] 메뉴 페이지 정상 수신({len(html)}바이트)했으나 "
                    "영양정보 없음 - 미공개로 판단"),
            })
    return out, True


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--brand", help="한 브랜드만 재조사")
    parser.add_argument("--status", default="unknown", help="재조사할 status (기본 unknown)")
    parser.add_argument("--dry-run", action="store_true", help="CSV를 쓰지 않고 결과만 출력")
    parser.add_argument("--max-urls", type=int, default=24,
                        help="브랜드당 요청 수 상한 (기본 24). 경로 우선 순회라 "
                             "24면 기록된 경로 + 상위 경로 몇 개를 3개 호스트에 모두 시도")
    args = parser.parse_args()

    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    targets = [r for r in rows
               if (r["brand"] == args.brand if args.brand else r["status"] == args.status)]
    if not targets:
        raise SystemExit(f"재조사 대상 없음 (brand={args.brand}, status={args.status})")

    print(f"재조사 대상 {len(targets)}개 브랜드, 브랜드당 최대 {args.max_urls} URL 시도\n")

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(probe, r["brand"], r, args.max_urls): r["brand"] for r in targets}
        for fut in concurrent.futures.as_completed(futures):
            brand = futures[fut]
            try:
                results[brand] = fut.result()
            except Exception as e:
                print(f"  [error] {brand}: {type(e).__name__}: {e}")

    today = date.today().isoformat()
    improved = 0
    by_brand = {r["brand"]: r for r in rows}
    for brand, (updated, learned) in results.items():
        before = by_brand[brand]
        if learned:
            updated["surveyed_at"] = today
            improved += 1
        arrow = f"{before['status']} -> {updated['status']}"
        print(f"  {brand:<12} {arrow:<22} {updated['nutrition_format']:<14} "
              f"{updated['nutrients'][:40]}")
        by_brand[brand] = updated

    if args.dry_run:
        print(f"\n--dry-run: CSV 미변경 ({improved}개 갱신 예정)")
        return

    status_order = {"adopted": 0, "viable": 1, "unknown": 2, "rejected": 3}
    out_rows = sorted(by_brand.values(),
                      key=lambda r: (status_order.get(r["status"], 9), r["category"], r["brand"]))
    with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        w.writeheader()
        w.writerows(out_rows)

    counts = {}
    for r in out_rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print(f"\n{CSV_PATH.relative_to(ROOT)} 갱신: {improved}개 브랜드 정보 채움")
    for s in ["adopted", "viable", "unknown", "rejected"]:
        if s in counts:
            print(f"  {s}: {counts[s]}")


if __name__ == "__main__":
    main()
