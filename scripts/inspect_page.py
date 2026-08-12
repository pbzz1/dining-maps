"""Print a compact structural summary of a menu page.

Exists to keep the crawler-writing loop cheap. Writing a parser needs maybe 20
lines of structural facts -- which tables exist, what their headers are, where
the nutrition numbers live -- but getting those by dumping raw HTML means
wading through 100KB of markup. This prints the 20 lines.

    python scripts/inspect_page.py https://www.hollys.co.kr/menu/espresso.do
    python scripts/inspect_page.py <url> --mobile      # if desktop UA 403s
    python scripts/inspect_page.py <url> --full        # + a text sample

Paste the output back into the conversation and a real parser can be written
against it, no re-fetching required.

Reading the output:

  tables=0 but nutrition keywords present  -> data is in div/li markup, or the
                                              page is JS-rendered
  tables=0 and no keywords, tiny page      -> JS-rendered; needs the browser
                                              tools, not urllib
  a table whose headers include 나트륨/단백질 -> parse_table + row_from_headers
                                              will already work
"""
import argparse
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from crawl_common import NUTRIENT_LABELS, clean, fetch, match_nutrient  # noqa: E402

MAX_HEADERS = 14
MAX_SAMPLE_ROWS = 2


def summarize(html, *, full=False):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = clean(soup.get_text(" "))

    print(f"length: {len(html):,} bytes of HTML, {len(text):,} chars of text")

    hits = [kw for _, kws in NUTRIENT_LABELS for kw in kws if kw in text]
    print(f"nutrition keywords: {', '.join(sorted(set(hits))) if hits else 'NONE'}")

    # A page that ships almost no text but plenty of markup is a JS shell.
    if len(text) < 500 and len(html) > 5000:
        print("!! very little text for this much HTML -- almost certainly JS-rendered")

    tables = soup.find_all("table")
    print(f"\ntables: {len(tables)}")
    for i, table in enumerate(tables):
        rows = table.find_all("tr")
        header_row = next((r for r in rows if r.find("th")), rows[0] if rows else None)
        if header_row is None:
            continue
        headers = [clean(c.get_text()) for c in header_row.find_all(["th", "td"])]
        mapped = [h for h in headers if match_nutrient(h)]
        flag = "  <-- NUTRITION TABLE" if mapped else ""
        print(f"  [{i}] {len(rows)} rows, {len(headers)} cols{flag}")
        print(f"      headers: {headers[:MAX_HEADERS]}")
        if mapped:
            print(f"      mapped:  {[(h, match_nutrient(h)) for h in headers if match_nutrient(h)]}")
            for tr in rows[1:1 + MAX_SAMPLE_ROWS]:
                cells = [clean(c.get_text()) for c in tr.find_all(["td", "th"])]
                if cells:
                    print(f"      sample:  {cells[:MAX_HEADERS]}")

    dls = soup.find_all("dl")
    if dls:
        print(f"\ndl blocks: {len(dls)}")
        for dl in dls[:3]:
            dt = dl.find("dt")
            print(f"  dt={clean(dt.get_text())[:40] if dt else '?'!r} "
                  f"text={clean(dl.get_text(' '))[:120]!r}")

    # Where do the numbers actually sit? Class names are the fastest route to a
    # CSS selector when there's no table to key off.
    classed = {}
    for kw in set(hits):
        for node in soup.find_all(string=re.compile(re.escape(kw))):
            parent = node.parent
            for _ in range(3):
                if parent is None:
                    break
                cls = " ".join(parent.get("class", []))
                if cls:
                    classed.setdefault(cls, set()).add(kw)
                    break
                parent = parent.parent
    if classed:
        print("\ncontainers holding nutrition text (class -> keywords):")
        for cls, kws in list(classed.items())[:10]:
            print(f"  .{cls}: {sorted(kws)}")

    if full:
        idx = min((text.find(kw) for kw in hits if text.find(kw) >= 0), default=-1)
        if idx >= 0:
            print(f"\ntext around first nutrition keyword:\n  {text[max(0, idx - 150):idx + 350]!r}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--mobile", action="store_true", help="use a mobile User-Agent")
    parser.add_argument("--full", action="store_true", help="also print a text sample")
    args = parser.parse_args()

    try:
        html = fetch(args.url, mobile=args.mobile)
    except Exception as e:
        raise SystemExit(f"fetch failed: {type(e).__name__}: {e}")
    summarize(html, full=args.full)


if __name__ == "__main__":
    main()
