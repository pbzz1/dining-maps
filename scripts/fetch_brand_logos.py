"""Fetch each brand's own site icon (apple-touch-icon / favicon) and save it
as a square PNG under frontend-react/public/logos/<slug>.png.

BrandAvatar.jsx already renders /logos/<slug>.png when the file exists and
falls back to a colored monogram otherwise (frontend-react/src/components/
BrandAvatar.jsx) -- this script is the "crawl the logo in" half of that,
nothing in the frontend needs to change to pick these up.

Site icons, not full wordmark logos: BrandAvatar renders into a 56px circle
with object-fit: cover, and a wide wordmark ("BURGER KING") cropped into a
circle is unreadable. A site's own apple-touch-icon/favicon is already a
square-ish mark meant to survive being shown small, which is exactly what a
monogram-replacement avatar needs -- and every brand publishes one at a
predictable, scriptable location, unlike a curated "correct" logo file.

Re-run anytime; it overwrites existing files, so brand icon updates just
mean running this again.

    python scripts/fetch_brand_logos.py
"""
import sys
import urllib.parse
from io import BytesIO
from pathlib import Path

from bs4 import BeautifulSoup
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from crawl_common import fetch  # noqa: E402
from crawl_common import DESKTOP_UA, _UNVERIFIED_CTX  # noqa: E402

import ssl
import urllib.error
import urllib.request

OUT_DIR = ROOT / "frontend-react" / "public" / "logos"
SIZE = 128

# name -> homepage URL. Same domains the crawlers already hit (see
# scripts/crawl_viable_brands.py and data/brand_survey.csv) plus the five
# original brands', which never needed a domain on file until now.
BRAND_SITES = {
    "mcdonalds": "https://www.mcdonalds.co.kr",
    # lotteria.com doesn't resolve at all from here; lotteeatz.com is the
    # real active site the crawler already POSTs to for menu data.
    "lotteria": "https://www.lotteeatz.com",
    "momstouch": "https://www.momstouch.co.kr",
    "subway": "https://www.subway.co.kr",
    "salady": "https://www.salady.com",
    "burgerking": "https://www.burgerking.co.kr",
    "starbucks": "https://www.starbucks.co.kr",
    "ediya": "https://www.ediya.com",
    "bhc": "https://www.bhc.co.kr",
    # kyochon.com's root is a meta-refresh stub with no <head> icon links --
    # /main/ is the page it redirects a browser to.
    "kyochon": "https://kyochon.com/main/",
    "pokeallday": "https://pokeallday.co.kr",
    "baskinrobbins": "https://www.baskinrobbins.co.kr",
    "paikdabang": "https://paikdabang.com",
    "coffeebean": "https://www.coffeebeankorea.com",
    "hollys": "https://www.hollys.co.kr",
    # same story as kyochon: www.dominos.co.kr root is a JS redirect to /gate.
    "dominos": "https://www.dominos.co.kr/gate",
}

ICON_RELS = ("apple-touch-icon", "apple-touch-icon-precomposed", "icon", "shortcut icon")


def fetch_bytes(url: str, timeout: int = 20) -> bytes:
    """Same verified-then-unverified SSL fallback as crawl_common.fetch, but
    returning raw bytes -- an icon is binary, fetch() always text-decodes."""
    req = urllib.request.Request(url, headers={"User-Agent": DESKTOP_UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.URLError as e:
        if hasattr(e, "close"):
            e.close()
        if not isinstance(getattr(e, "reason", None), ssl.SSLError):
            raise
        with urllib.request.urlopen(req, timeout=timeout, context=_UNVERIFIED_CTX) as resp:
            return resp.read()


def icon_candidates(site: str) -> list[str]:
    """<link rel="...icon..."> URLs from the homepage, largest declared
    `sizes` first, then the two conventional fallback paths every site is
    expected to answer even with no <link> at all."""
    candidates = []
    try:
        html = fetch(site)
        soup = BeautifulSoup(html, "html.parser")
        tagged = []
        for link in soup.find_all("link", rel=True):
            rel = " ".join(link.get("rel")).lower()
            if any(r in rel for r in ICON_RELS):
                href = link.get("href")
                if not href:
                    continue
                sizes = link.get("sizes", "")
                width = int(sizes.split("x")[0]) if "x" in sizes and sizes.split("x")[0].isdigit() else 0
                is_apple = "apple-touch-icon" in rel
                tagged.append((is_apple, width, urllib.parse.urljoin(site, href)))
        tagged.sort(key=lambda t: (t[0], t[1]), reverse=True)
        candidates.extend(url for *_, url in tagged)
    except Exception as e:
        print(f"  [warn] {site}: homepage fetch failed ({e})")
    candidates += [urllib.parse.urljoin(site, "/apple-touch-icon.png"),
                   urllib.parse.urljoin(site, "/favicon.ico")]
    # de-dupe, keep order
    seen = set()
    return [c for c in candidates if not (c in seen or seen.add(c))]


def save_square_png(raw: bytes, out_path: Path) -> bool:
    try:
        img = Image.open(BytesIO(raw))
        img.load()
    except Exception:
        return False
    if img.width < 16 or img.height < 16:
        return False  # tracking-pixel-sized "icon", not a real mark -- a
        # genuine 16px favicon (still common on older KR sites) is blurry
        # once upscaled to SIZE but is the site's real mark, not garbage
    img = img.convert("RGBA")
    side = max(img.width, img.height)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(img, ((side - img.width) // 2, (side - img.height) // 2), img)
    canvas.resize((SIZE, SIZE), Image.LANCZOS).save(out_path)
    return True


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok, failed = [], []
    for slug, site in BRAND_SITES.items():
        for url in icon_candidates(site):
            try:
                raw = fetch_bytes(url)
            except Exception:
                continue
            if save_square_png(raw, OUT_DIR / f"{slug}.png"):
                ok.append(slug)
                print(f"  {slug}: {url}")
                break
        else:
            failed.append(slug)
            print(f"  [fail] {slug}: no usable icon found at {site}")
    print(f"\n{len(ok)}/{len(BRAND_SITES)} logos saved to {OUT_DIR}")
    if failed:
        print(f"missing (falls back to monogram): {', '.join(failed)}")


if __name__ == "__main__":
    main()
