"""Shared helpers for the per-brand nutrition crawlers.

The five original crawlers (mcdonalds/lotteria/subway/salady + hand-transcribed
momstouch) each grew their own fetch/parse code. That was fine at five brands;
at fifteen it means fifteen copies of the same SSL-fallback and
number-normalization logic. Everything reusable lives here instead.

Two things worth knowing before editing:

1. `write_csv` emits the exact column names load_data.py's FILES mapping
   expects. Add a nutrient here and you must add it there too, or it silently
   never reaches the DB.
2. `extract_nutrients` is a *label-driven* parser, not a position-driven one.
   Korean franchise nutrition tables reorder columns between redesigns, so
   matching on the header text ("나트륨") survives a redesign that matching on
   "the 5th <td>" does not. crawl_lotteria.py learned this the hard way -- see
   the column-shift bug in docs/data_quality.md.
"""
import csv
import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT / "data"

# Several franchise sites (eggdrop, bonif) serve incomplete cert chains. We
# still want their data; we're reading public menu pages, not sending secrets.
_UNVERIFIED_CTX = ssl.create_default_context()
_UNVERIFIED_CTX.check_hostname = False
_UNVERIFIED_CTX.verify_mode = ssl.CERT_NONE

DESKTOP_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
# Some brands (교촌, KFC) expose nutrition only on their m. subdomain, and a
# few 403 a desktop UA outright.
MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")

# The canonical CSV schema. Order matters only for human readability; load_data
# reads by column name.
STANDARD_COLUMNS = [
    "restaurant", "menu_name", "menu_category", "weight_g", "price_krw",
    "calorie_kcal", "protein_g", "sugar_g", "saturated_fat_g", "sodium_mg",
    "caffeine_mg",
    # Blank means per-serving, the convention 맥도날드/롯데리아/서브웨이 use.
    # BHC and 교촌 publish per-100g instead, and the two cannot be shown side
    # by side without saying which is which -- "266 kcal" means a light snack
    # for one and a whole chicken for the other. Grades are unaffected (the
    # score divides nutrients by calories, so a uniform scale cancels), but
    # any displayed or compared raw value needs this column.
    "nutrition_basis",
    # 제품 전체 중량 (weight_g가 1회분일 때만 의미). 도미노가 1회분 150g 옆에 한 판
    # 총중량을 나란히 공개해서, 점수는 1회분으로 매기되 신메뉴 화면은 한 판으로
    # 환산해 보여줄 수 있다. 다른 브랜드는 비워둔다.
    "total_weight_g",
]

# Label -> CSV column. Longer/more specific labels must be tried first:
# "포화지방" contains "지방", and 트랜스지방 would otherwise match 지방 too.
# extract_nutrients relies on this dict being ordered (Python 3.7+ guarantee).
NUTRIENT_LABELS = [
    ("saturated_fat_g", ["포화지방산", "포화지방"]),
    ("calorie_kcal", ["열량", "칼로리", "에너지", "kcal"]),
    ("protein_g", ["단백질"]),
    ("sugar_g", ["당류", "당分", "총당류"]),
    ("sodium_mg", ["나트륨"]),
    ("caffeine_mg", ["카페인"]),
]

# Values we should never write: these mean "not disclosed", not "zero".
_NULLISH = {"", "-", "--", "n/a", "N/A", "해당없음", "없음", "미표기", "."}


def fetch(url, *, timeout=20, mobile=False, headers=None, data=None, as_json=False,
          referer=None, encoding="utf-8"):
    """GET (or POST, if `data` is given) with the SSL fallback every crawler needs.

    Returns decoded text, or a parsed object when as_json=True. Raises the
    original urllib error if both the verified and unverified attempts fail --
    callers decide whether a brand failing is fatal.

    `encoding` defaults to utf-8, which is what nearly every brand site uses.
    A handful of older ASP/JSP sites (도미노피자's ingredient page is the one
    found so far) still serve euc-kr and need it passed explicitly -- decoding
    those as utf-8 doesn't raise, it just produces mojibake, so this has to be
    set by the caller rather than detected from a decode failure.
    """
    hdrs = {"User-Agent": MOBILE_UA if mobile else DESKTOP_UA,
            "Accept-Language": "ko-KR,ko;q=0.9"}
    if referer:
        hdrs["Referer"] = referer
    if data is not None and not isinstance(data, bytes):
        if isinstance(data, dict):
            data = urllib.parse.urlencode(data).encode()
            hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded")
        else:
            data = str(data).encode()
    if headers:
        hdrs.update(headers)

    req = urllib.request.Request(url, headers=hdrs, data=data)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.URLError as e:
        # An HTTPError *is* a response object, and leaving it unclosed makes
        # Python 3.14 print an "Exception ignored while finalizing" traceback
        # at GC time. That looks exactly like a crash in the middle of an
        # otherwise-successful run, so close it before moving on.
        if hasattr(e, "close"):
            e.close()
        # Only retry unverified for cert problems -- a 404 shouldn't be retried.
        if not isinstance(getattr(e, "reason", None), ssl.SSLError):
            raise
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_UNVERIFIED_CTX) as resp:
                raw = resp.read()
        except urllib.error.URLError as retry_error:
            if hasattr(retry_error, "close"):
                retry_error.close()
            raise

    text = raw.decode(encoding, errors="replace")
    return json.loads(text) if as_json else text


def num(value):
    """Pull the first number out of a label cell, or '' if there isn't one.

    Handles the formats Korean nutrition tables actually use:
      "1,234"      -> 1234      (thousands separator)
      "12.5 g"     -> 12.5      (trailing unit)
      "0.5g 미만"  -> 0.5       (below-threshold notation)
      "5 (10%)"    -> 5         (value with %DV in parens)
      "-", "해당없음" -> ''       (not disclosed -- must NOT become 0)
    """
    if value is None:
        return ""
    s = str(value).strip()
    if s in _NULLISH:
        return ""
    s = s.replace(",", "")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    if not m:
        return ""
    out = m.group(0)
    # "0.5g 미만" / "미만 0.5g" -- report the stated bound, same as crawl_lotteria.
    return out


def clean(text):
    """Collapse the whitespace that server-rendered Korean pages are full of."""
    if text is None:
        return ""
    return re.sub(r"\s+", " ", str(text)).replace("\xa0", " ").strip()


def match_nutrient(label):
    """Map a table header / dt label to a CSV column, or None if unrelated."""
    lab = clean(label).lower()
    if not lab:
        return None
    for column, keywords in NUTRIENT_LABELS:
        for kw in keywords:
            if kw.lower() in lab:
                return column
    return None


def extract_nutrients(text):
    """Scrape 'label 123 unit' pairs out of a free-text blob.

    The fallback for brands whose markup we haven't inspected: it doesn't care
    about tags at all, only about a nutrient word followed by a number. Good
    enough to confirm a page *has* usable data; replace with a real parser once
    the structure is known (see scripts/survey/inspect_page.py).
    """
    flat = clean(text)
    out = {}
    for column, keywords in NUTRIENT_LABELS:
        for kw in keywords:
            # label, optional colon/parenthetical unit, then the number
            m = re.search(rf"{re.escape(kw)}\s*[:\(]?\s*(?:\([^)]*\)\s*)?([\d,]+(?:\.\d+)?)", flat)
            if m:
                out[column] = num(m.group(1))
                break
    return out


def parse_table(table):
    """Turn a <table> into row dicts keyed by header text.

    Assumes the first row containing <th> (or the first row overall) is the
    header. Rows with a different cell count than the header are skipped rather
    than zip-truncated -- a truncated row is exactly how the Lotteria column
    shift went unnoticed.
    """
    rows = table.find_all("tr")
    if not rows:
        return []

    header_row = next((r for r in rows if r.find("th")), rows[0])
    headers = [clean(c.get_text()) for c in header_row.find_all(["th", "td"])]
    if not headers:
        return []

    out = []
    for tr in rows:
        if tr is header_row:
            continue
        cells = tr.find_all(["td", "th"])
        if len(cells) != len(headers):
            continue
        out.append({h: clean(c.get_text()) for h, c in zip(headers, cells)})
    return out


def row_from_headers(raw_row, *, restaurant, name_keys=("메뉴", "제품", "상품", "품목", "이름"),
                     category=None):
    """Convert one header-keyed dict into a STANDARD_COLUMNS row.

    Picks the menu name from whichever column looks like a name column, and
    maps every other column through match_nutrient. Returns None when there's
    no usable name, so callers can just filter falsy results.
    """
    row = {c: "" for c in STANDARD_COLUMNS}
    row["restaurant"] = restaurant
    row["menu_category"] = category or ""

    for key, value in raw_row.items():
        k = clean(key)
        if not row["menu_name"] and any(nk in k for nk in name_keys):
            row["menu_name"] = clean(value)
            continue
        if "중량" in k or "총량" in k or re.search(r"\(\s*g\s*\)$", k):
            row["weight_g"] = row["weight_g"] or num(value)
            continue
        if "가격" in k or "금액" in k or "원" == k:
            row["price_krw"] = row["price_krw"] or num(value)
            continue
        column = match_nutrient(k)
        if column and not row[column]:
            row[column] = num(value)

    if not row["menu_name"]:
        # Fall back to the first non-numeric cell -- some tables label the name
        # column "구분" or leave the header blank entirely.
        for value in raw_row.values():
            v = clean(value)
            if v and not re.fullmatch(r"[\d,.\s]+", v):
                row["menu_name"] = v
                break
    return row if row["menu_name"] else None


def has_any_nutrient(row):
    """True if a row carries at least one real nutrition number.

    Rows that are pure name+category are noise -- they'd inflate the row count
    that snapshot_and_validate.py's row_count_stability check watches, hiding a
    real regression behind a pile of empty rows.
    """
    return any(row.get(c) not in (None, "") for c, _ in NUTRIENT_LABELS)


def write_csv(rows, filename, *, extra_columns=()):
    """Write rows to data/<filename> using the canonical column order."""
    rows = [r for r in rows if r]
    # 사이트 개편으로 파서가 0행을 내면 기존 CSV를 빈 파일로 덮어써 버린다.
    # 무인 크롤(GitHub Actions)이 그걸 그대로 커밋하면 안 되니 실패로 처리 --
    # 드라이버의 브랜드별 try/except가 FAILED로 집계하고 기존 CSV는 살아남는다.
    if not rows:
        raise ValueError(f"0 rows for {filename} -- refusing to overwrite existing CSV")
    columns = list(STANDARD_COLUMNS) + [c for c in extra_columns if c not in STANDARD_COLUMNS]
    path = DATA_DIR / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in columns})
    return path
