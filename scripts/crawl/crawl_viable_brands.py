"""Crawl the 10 brands marked `viable` in data/brand_survey.csv.

`viable` means the survey confirmed the brand publishes nutrition data but no
data/<brand>.csv exists yet. This script closes that gap.

    python scripts/crawl/crawl_viable_brands.py --list
    python scripts/crawl/crawl_viable_brands.py --brand starbucks
    python scripts/crawl/crawl_viable_brands.py                 # all of them

Run it per-brand while iterating; one brand failing shouldn't cost you the
other nine. Each parser writes data/<slug>.csv and prints a row count, and
--all keeps going past a failure and reports the tally at the end.

## Confidence levels

All eleven parsers below are now VERIFIED -- each one was checked against
real output (row counts, spot-checked values) rather than left as a guess
from the survey's keyword probe. That confidence level lives in the
CRAWLERS dict, not in this comment, so it can't drift out of sync silently.

Several of the survey's original findings turned out to be wrong once a
parser was actually written against the live page, not just close-but-off:
BHC and 포케올데이's recorded URLs had no real per-product data at all (one
was an empty template, the other a single daily-%DV reference row);
버거킹's recorded API had price but not nutrition (the real nutrition
endpoint, BKR0347, wasn't in the survey at all, and burgerking.co.kr's WAF
blocks urllib/curl outright -- see crawl_burgerking's docstring); 교촌치킨's
mobile API lacks 당류/포화지방 entirely (the PC site has them -- 2026-08-23). If a
brand's row count or nutrient coverage looks surprising, check the parser's
own docstring first -- most of them document exactly this kind of correction.

Nothing here writes to the DB. Feed the CSVs through the normal path so the
quality gate still applies:

    python scripts/pipeline/snapshot_and_validate.py && python scripts/pipeline/load_data.py
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from crawl_common import (  # noqa: E402
    STANDARD_COLUMNS, clean, extract_nutrients, fetch, has_any_nutrient,
    match_nutrient, num, parse_table, row_from_headers, write_csv,
)

REQUEST_DELAY = 0.3  # be a polite guest on someone else's menu server


def blank_row(restaurant, name, category=""):
    row = {c: "" for c in STANDARD_COLUMNS}
    row["restaurant"] = restaurant
    row["menu_name"] = clean(name)
    row["menu_category"] = category
    return row


# --------------------------------------------------------------------------
# 버거킹 -- VERIFIED, but NOT reproducible with plain urllib. Read this before
# touching this function.
# --------------------------------------------------------------------------
#
# What the survey got wrong: it recorded BKR0632 (list) + BKR0634 (detail) as
# carrying nutrition directly, with dineInprc as the price field. Both facts
# turned out to be false once actually inspected in a browser:
#
#   BKR0632.json  -- product list. Name + image + code only. No nutrition.
#   BKR0634.json  -- per-product detail. Has dineInprc (price) and
#                    menuCalorie, but NOT protein/sugar/sodium/fat/caffeine.
#   BKR0347.json  -- the real nutrition source. One call, no params, returns
#                    ALL ~220 products' full nutrition keyed by *name*
#                    (menuNm), not by product code. Fields: calory, protein,
#                    sugars, satufat, natrium, caffein, weight. protein/
#                    satufat/natrium come as "value(%DV)", e.g. "2146(107)" --
#                    keep only the part before "(".
#
# Why plain urllib/curl can't drive this: burgerking.co.kr sits behind a WAF
# that resets the TLS handshake for both Python's ssl module and curl on this
# network -- confirmed by testing curl with a real browser UA + a session
# cookie from an initial GET, which worked exactly once before being blocked
# again. It looks like a low request-budget bot check rather than a simple
# UA/cookie gate, so retrying with backoff is unlikely to help reliably.
#
# What actually works: driving the site from an already-loaded browser tab
# and issuing the same `fetch()` calls the page's own JS makes (the WAF has
# already cleared that session). data/burgerking.csv (85 rows, nutrition +
# price) was produced exactly that way on 2026-08-12 -- see the message
# envelope format below, captured by monkey-patching window.fetch on the live
# menu page and clicking through it.
#
# This function is intentionally NOT a working urllib crawler. It documents
# the request shape so a future re-crawl (when the CSV goes stale) knows
# what to replay from a browser console, rather than re-deriving it from
# scratch against a WAF that blocks the naive approach.
def crawl_burgerking():
    raise NotImplementedError(
        "burgerking.co.kr blocks urllib/curl at the TLS layer (connection reset "
        "on POST to /burgerking/*.json even with a valid session cookie -- "
        "confirmed 2026-08-12). Re-crawl by opening "
        "https://www.burgerking.co.kr/menu/list/all in a real browser and, from "
        "the page's own JS context, POSTing this envelope to "
        "/burgerking/BKR0347.json (no per-product args -- returns all ~220 "
        "items' nutrition at once, keyed by menuNm):\n\n"
        '  message=' + json.dumps({
            "header": {"result": True, "error_code": "", "error_text": "",
                      "info_text": "", "message_version": "", "login_session_id": "",
                      "trcode": "BKR0347", "cd_call_chnn": "01"},
            "body": {},
        }, ensure_ascii=False) + "\n\n"
        "Prices aren't in that response -- fetch BKR0632.json the same way for "
        "the {menuCd: menuNm} list, then BKR0634.json per menuCd (same envelope, "
        "body={\"menuCd\": <code>}) for dineInprc. ~250 products, one call each, "
        "took ~30s total from within the page. Join nutrition to price by "
        "matching menuNm between BKR0347 and BKR0632, and drop rows whose "
        "calory is 0 (free add-ons / discontinued placeholders, not real items)."
    )


# --------------------------------------------------------------------------
# 스타벅스 -- VERIFIED via browser network inspection. The survey's
# "product_cd on the list page, then visit drink_view.do per product" plan
# doesn't work: drink_list.do renders 11 empty <table class="coffeeInfo">
# shells (one per category) with no product_cd anywhere in the static HTML --
# the browser fills them in from these per-category JSON files instead.
# --------------------------------------------------------------------------
STARBUCKS_CATEGORIES = {
    "W0000171": "콜드 브루 커피", "W0000060": "브루드 커피", "W0000003": "에스프레소",
    "W0000004": "프라푸치노", "W0000005": "블렌디드", "W0000422": "리프레셔",
    "W0000061": "피지오", "W0000075": "티(티바나)", "W0000053": "기타 제조 음료",
    "W0000062": "스타벅스 주스(병음료)",
}
STARBUCKS_JSON_URL = "https://www.starbucks.co.kr/upload/json/menu/{code}.js"

# API field -> CSV column. sat_FAT/sugars/protein/sodium/caffeine/kcal are all
# base-size (Tall-equivalent) values; the _L-suffixed twins are the Large
# variant and are intentionally not read here, matching the survey's
# "Tall 사이즈 기준" note.
_STARBUCKS_FIELDS = {
    "calorie_kcal": "kcal", "protein_g": "protein", "sugar_g": "sugars",
    "saturated_fat_g": "sat_FAT", "sodium_mg": "sodium", "caffeine_mg": "caffeine",
}


def crawl_starbucks():
    """One static JSON file per category (found via the site's own category-code
    switch statement), each holding every product's full nutrition already --
    no per-product page needed."""
    rows = []
    for code, category in STARBUCKS_CATEGORIES.items():
        try:
            data = fetch(STARBUCKS_JSON_URL.format(code=code), as_json=True)
        except Exception as e:
            print(f"  [warn] 스타벅스 {category} ({code}): {e}")
            continue
        products = data.get("list", [])
        for product in products:
            name = clean(product.get("product_NM"))
            if not name:
                continue
            row = blank_row("스타벅스", name, category)
            for column, key in _STARBUCKS_FIELDS.items():
                row[column] = num(product.get(key))
            if has_any_nutrient(row):
                rows.append(row)
        print(f"  스타벅스 {category}: {len(products)}개")
        time.sleep(REQUEST_DELAY)
    return _dedupe(rows), "starbucks.csv"


# --------------------------------------------------------------------------
# 이디야 -- VERIFIED (survey: dl/dt/dd inline on the list page, no detail pages)
# --------------------------------------------------------------------------
EDIYA_AJAX = ("https://www.ediya.com/inc/ajax_brand.php"
              "?gubun=menu_more&product_cate={cate}&chked_val=&skeyword=&page={page}")


def crawl_ediya():
    """Page through 이디야's own "더보기" AJAX endpoint, 8 drinks at a time.

    The survey said nutrition sits inline on the list page needing no
    pagination. Half right: it is inline, but the page ships only the first 8
    items and the rest arrive from this endpoint, so parsing drink.html
    directly yielded 6 rows out of ~200.

    Two traps worth naming. The endpoint answers only to POST (a GET returns
    the same first page forever, which looks like working pagination until you
    diff the names). And it never sends the documented "none" terminator
    within any sane page count, so the loop stops when a page stops
    contributing new products instead of trusting the sentinel.
    """
    rows = []
    for cate, category in ((7, "음료"), (8, "푸드")):
        seen_before = len(rows)
        for page in range(1, 40):
            try:
                html = fetch(EDIYA_AJAX.format(cate=cate, page=page), data=b"")
            except Exception as e:
                print(f"  [warn] 이디야 cate={cate} page={page}: {e}")
                break
            if html.strip() in ("", "none"):
                break

            soup = BeautifulSoup(html, "html.parser")
            page_rows = [_ediya_row(li, category) for li in soup.select("li")]
            page_rows = [r for r in page_rows if r]
            if not page_rows:
                break

            before = {(r["restaurant"], r["menu_name"]) for r in rows}
            rows.extend(page_rows)
            if not {(r["restaurant"], r["menu_name"]) for r in page_rows} - before:
                break  # nothing new -- the endpoint has started repeating
            time.sleep(REQUEST_DELAY)
        print(f"  이디야 {category}: {len(rows) - seen_before}행")
    return _dedupe(rows), "ediya.csv"


def _ediya_row(li, category):
    """One <li>: <h2> name (English name in a nested <span>), <dl> per nutrient."""
    heading = li.select_one(".pro_detail h2, .detail_con h2")
    if not heading:
        return None
    # Drop the nested English name so "(L) 얼박사 코코 에이드 (L) Ice Bac ..."
    # doesn't become the product name.
    for span in heading.find_all("span"):
        span.decompose()
    name = clean(heading.get_text())
    if not name:
        return None

    row = blank_row("이디야", name, category)
    for dl in li.select(".pro_nutri dl"):
        dt, dd = dl.find("dt"), dl.find("dd")
        if not dt or not dd:
            continue
        column = match_nutrient(dt.get_text())
        if column:
            row[column] = num(dd.get_text())

    size = li.select_one(".pro_size")
    if size:
        text = clean(size.get_text())
        # "컵용량 : 520ml" is a drink volume, not a food weight -- only record
        # it when the unit really is grams.
        if re.search(r"\d\s*g\b", text):
            row["weight_g"] = num(text)
    return row if has_any_nutrient(row) else None


# --------------------------------------------------------------------------
# BHC -- VERIFIED (survey: server-rendered <table>, Lotteria-like structure)
# --------------------------------------------------------------------------
BHC_API = "https://www.bhc.co.kr/api/v1/web"


def crawl_bhc():
    """Walk BHC's own JSON API: categories -> products -> per-product detail.

    The survey recorded BHC as a server-rendered <table>, which was wrong. The
    /menu pages do contain a nutrition table, but it ships empty (every cell
    "-") and React fills it in from these endpoints -- so the HTML parser
    scraped 0 rows. The endpoints came out of the browser's network log.

    IMPORTANT -- values are per 100g, not per serving. A 10호 chicken weighs
    951-1,050g but reports 266 kcal, which only makes sense as a 100g figure.
    That doesn't affect the diet grade (scoring divides nutrients by calories,
    so any uniform scale cancels out) but it does make the raw calorie number
    incomparable to 맥도날드's per-serving figures, so `nutrition_basis` is
    recorded per row rather than silently mixed in.
    """
    categories = fetch(f"{BHC_API}/categories/list", as_json=True)["body"]

    # A product can be listed under several categories; keep the first.
    products = {}
    for category in categories:
        try:
            listing = fetch(f"{BHC_API}/categories/{category['cateIdx']}/products",
                            as_json=True)["body"]
        except Exception as e:
            print(f"  [warn] BHC 카테고리 {category['cateNm']}: {e}")
            continue
        for product in listing:
            products.setdefault(product["productCd"], category["cateNm"])
        time.sleep(REQUEST_DELAY)

    print(f"  BHC: 카테고리 {len(categories)}개, 상품 {len(products)}개")

    rows = []
    for code, category in products.items():
        try:
            detail = fetch(f"{BHC_API}/products/{code}", as_json=True)["body"]
        except Exception as e:
            print(f"  [warn] BHC 상품 {code}: {e}")
            continue

        # flavorNutrition carries per-flavour variants; mainNutrition the base
        # product. Both use the same field names.
        entries = [detail.get("mainNutrition")] + list(detail.get("flavorNutrition") or [])
        for entry in entries:
            row = _bhc_row(detail, entry, category)
            if row:
                rows.append(row)
        time.sleep(REQUEST_DELAY)
    return _dedupe(rows), "bhc.csv"


# The API publishes carbs/fat/cholesterol too; only the five diet_score uses
# plus weight/price are carried across.
_BHC_NUTRIENTS = {
    "calorie_kcal": "calories",
    "protein_g": "proteins",
    "sugar_g": "sugars",
    "saturated_fat_g": "saturatedFat",
    "sodium_mg": "sodium",
}


def _bhc_row(detail, entry, category):
    if not entry or not str(entry.get("calories", "")).strip():
        return None
    name = clean(entry.get("itemNm") or detail.get("productNm"))
    if not name:
        return None

    row = blank_row("BHC", name, category)
    for column, key in _BHC_NUTRIENTS.items():
        row[column] = num(entry.get(key))
    row["price_krw"] = num(detail.get("price"))
    # weight is prose ("10호(951g~1,050g)" plus a paragraph of caveats), so the
    # first number in it is a range bound, not a serving size -- don't pretend
    # otherwise by parsing it into weight_g.
    row["nutrition_basis"] = "per_100g"
    return row if has_any_nutrient(row) else None


# --------------------------------------------------------------------------
# 교촌치킨 -- VERIFIED. Nutrition from the PC site, price from the mobile API.
# --------------------------------------------------------------------------
KYOCHON_PC = "http://kyochon.com/menu"
KYOCHON_PC_CATEGORIES = {"chicken": "치킨", "side": "사이드", "drink": "음료",
                         "burger": "버거", "dream": "치킨", "newmenu": "", "liquor": "음료"}
KYOCHON_LIST_API = "https://m.kyochon.com/product/ProductSO/getProductListToMenu.do"


def crawl_kyochon():
    """PC site (kyochon.com/menu/view.asp?id=N) publishes the full 5-nutrient
    set -- 열량/당류/단백질/포화지방/나트륨 per 100g plus 조리 전 중량 -- which the
    mobile API (CALORIE/FAT/PROTEIN/CARBOHYDRATE/NATRIUM) never did; that gap is
    why this brand was unscorable until 2026-08-23. The PC detail page has no
    price, so SELL_PRICE is joined from the mobile listing API by product ID
    (both sites share the same IDs, e.g. 41363 = 간장윙박스20PCS).
    """
    ids = {}
    for cat, label in KYOCHON_PC_CATEGORIES.items():
        try:
            soup = BeautifulSoup(fetch(f"{KYOCHON_PC}/{cat}.asp"), "html.parser")
        except Exception as e:
            print(f"  [warn] 교촌치킨 {cat}: {e}")
            continue
        for a in soup.select('a[href*="view.asp"]'):
            m = re.search(r"id=(\d+)&cg=(\d+)", a["href"])
            if m:
                ids.setdefault(m.group(1), (m.group(2), label))
    print(f"  교촌치킨: 상품 {len(ids)}개")

    prices = {}
    try:
        listing = fetch(KYOCHON_LIST_API, data={"DEPTH1": "", "DEPTH2": ""}, as_json=True,
                        referer="https://m.kyochon.com/menu/menu_list")
        prices = {str(p.get("ID")): num(p.get("SELL_PRICE")) for p in listing["result"]["dataList"][0]["rows"]}
    except Exception as e:
        print(f"  [warn] 교촌치킨 price listing: {e}")

    labels = {"열량(Kcal)": "calorie_kcal", "당류(g)": "sugar_g", "단백질(g)": "protein_g",
              "포화지방(g)": "saturated_fat_g", "나트륨(mg)": "sodium_mg"}
    rows = []
    for pid, (cg, label) in ids.items():
        try:
            soup = BeautifulSoup(fetch(f"{KYOCHON_PC}/view.asp?id={pid}&cg={cg}"), "html.parser")
        except Exception as e:
            print(f"  [warn] 교촌치킨 {pid}: {e}")
            continue
        name = soup.select_one("dl.tit dt")
        table = soup.select_one(".linkCont table")
        if not name or not table:
            continue
        row = blank_row("교촌치킨", name.get_text(" ", strip=True), label)
        for tr in table.select("tbody tr"):
            tds = [clean(td.get_text(" ")) for td in tr.find_all("td")]
            if len(tds) == 2 and tds[0] in labels:
                row[labels[tds[0]]] = num(tds[1])
            elif tds and tds[0].startswith("조리 전 중량"):
                m = re.search(r"(\d[\d,]*)\s*g", tds[0])
                row["weight_g"] = m.group(1).replace(",", "") if m else ""
        basis = table.select_one("th span")
        row["nutrition_basis"] = "per_100g" if basis and "100g" in basis.get_text() else "per_serving"
        row["price_krw"] = prices.get(pid, "")
        if has_any_nutrient(row):
            rows.append(row)
        time.sleep(REQUEST_DELAY)
    return _dedupe(rows), "kyochon.csv"


# --------------------------------------------------------------------------
# 포케올데이 -- VERIFIED (2026-08-23: /nutrition_info now carries all 9 nutrients)
# --------------------------------------------------------------------------
POKEALLDAY_NUTRITION = "https://pokeallday.co.kr/nutrition_info"
# `.nutrition_sort_item_wrap.wrapN` -> category, read off the page's section order.
POKEALLDAY_WRAPS = {"wrap1": "베이스", "wrap2": "메인 토핑", "wrap3": "소스", "wrap4": "추가 토핑",
                    "wrap5": "밸런스박스", "wrap6": "프로틴포케", "wrap10": "저당 덮밥",
                    "wrap11": "메밀면 샐러드", "wrap9": "메밀면 샐러드", "wrap7": "사이드", "wrap8": "음료"}


def crawl_pokeallday():
    """/nutrition_info embeds every item as inline JS:
        { name: '곡물밥 <br> POKE', value: '원재료용량|열량|나트륨|탄수화물|당류|단백질|지방|콜레스테롤|포화지방산|트랜스지방' }
    one `let itemInfoArr` block per category. This is the only place the brand
    publishes 나트륨/당류/포화지방 -- the per-category menu cards (/poke etc.)
    that the previous parser scraped only list 중량/칼로리/탄수화물/단백질/지방,
    which is why this brand was unscorable until 2026-08-23. Values are per
    serving (원재료 용량); non-gram servings ("1ea", "12oz") leave weight_g blank.
    """
    html = fetch(POKEALLDAY_NUTRITION)
    rows = []
    for wrap, block in re.findall(r"nutrition_sort_item_wrap\.(wrap\d+)'\);\s*let itemInfoArr(.*?)</script>",
                                  html, flags=re.S):
        category = POKEALLDAY_WRAPS.get(wrap, "")
        for name, value in re.findall(r"name:\s*'([^']*)',\s*value:\s*'([^']*)'", block):
            parts = value.split("|")
            if len(parts) != 10:
                continue
            weight, cal, sodium, _carb, sugar, protein, _fat, _chol, sat_fat, _trans = parts
            row = blank_row("포케올데이", re.sub(r"<br\s*/?>", " ", name), category)
            row["weight_g"] = num(weight) if re.fullmatch(r"[\d.]+", weight.strip()) else ""
            row["calorie_kcal"] = num(cal)
            row["sodium_mg"] = num(sodium)
            row["sugar_g"] = num(sugar)
            row["protein_g"] = num(protein)
            row["saturated_fat_g"] = num(sat_fat)
            row["nutrition_basis"] = "per_serving"
            if has_any_nutrient(row):
                rows.append(row)
    print(f"  포케올데이: 상품 {len(rows)}개")
    return _dedupe(rows), "pokeallday.csv"


# --------------------------------------------------------------------------
# UNVERIFIED -- structure never inspected, generic extraction only.
# Expect to rewrite these once you've seen `inspect_page.py` output.
# --------------------------------------------------------------------------
def _generic_tables(restaurant, pages, csv_name):
    """Try parse_table on every <table>; fall back to per-block text scraping.

    Deliberately dumb: it works whenever the page uses a real table with
    labelled headers, and reports honestly (0 rows) when it doesn't, rather
    than emitting garbage that would sail through the quality gate.
    """
    rows = []
    for category, url in pages.items():
        try:
            html = fetch(url)
        except Exception as e:
            print(f"  [warn] {restaurant} {category}: {e}")
            continue
        soup = BeautifulSoup(html, "html.parser")

        for table in soup.find_all("table"):
            headers = [clean(th.get_text()) for th in table.find_all("th")]
            if not any(match_nutrient(h) for h in headers):
                continue  # not a nutrition table
            for raw in parse_table(table):
                row = row_from_headers(raw, restaurant=restaurant, category=category)
                if row and has_any_nutrient(row):
                    rows.append(row)

        if not rows:
            # No usable table -- try card/list markup: a heading plus nutrition
            # text inside the same block.
            for block in soup.select("li, .menu_list li, .item, .prod, article"):
                text = block.get_text(" ")
                nutrients = extract_nutrients(text)
                if not any(v != "" for v in nutrients.values()):
                    continue
                heading = block.find(["h2", "h3", "h4", "h5", "strong", "dt", "b"])
                name = clean(heading.get_text()) if heading else ""
                if not name:
                    continue
                row = blank_row(restaurant, name, category)
                row.update({k: v for k, v in nutrients.items() if v != ""})
                if has_any_nutrient(row):
                    rows.append(row)
        time.sleep(REQUEST_DELAY)
    return _dedupe(rows), csv_name


BASKINROBBINS_CATEGORIES = {"A": "아이스크림", "F": "프리팩", "B": "아이스크림케이크", "E": "디저트"}

_BR_LABELS = {
    "1회 제공량(g)": "weight_g", "열량(kcal)": "calorie_kcal", "당류(g)": "sugar_g",
    "단백질(g)": "protein_g", "포화지방(g)": "saturated_fat_g", "나트륨(mg)": "sodium_mg",
}


def crawl_baskinrobbins():
    """List each category to get real seq ids, then read the dt/dd nutrition
    block on each product's view page.

    The survey's blind seq range (1-120) would have hit unrelated seq values
    from other site sections (events, notices share the same view.php-style
    numbering) -- listing the 4 menu categories first (아이스크림/프리팩/
    아이스크림케이크/디저트) gives the real 95 product ids instead of guessing.
    Nutrition is a clean <dl> of dt/dd pairs (1회 제공량 first, then the five
    usual nutrients), so this reads that directly rather than the generic
    extract_nutrients() text scan.

    Only 아이스크림 (30/30 products) actually has this <dl> -- 프리팩/
    아이스크림케이크/디저트 view pages have no nutrition block at all
    (checked directly, not a parser miss). So this brand's CSV only ever
    covers scoops, not cakes or prepacks.
    """
    ids = {}
    for cat_code, category in BASKINROBBINS_CATEGORIES.items():
        try:
            html = fetch(f"https://www.baskinrobbins.co.kr/menu/list.php?category={cat_code}")
        except Exception as e:
            print(f"  [warn] 배스킨라빈스 {category}: {e}")
            continue
        for seq in sorted(set(re.findall(r"seq=(\d+)", html))):
            ids.setdefault(seq, category)
    print(f"  배스킨라빈스: 상품 {len(ids)}개")

    rows = []
    for seq, category in ids.items():
        try:
            html = fetch(f"https://www.baskinrobbins.co.kr/menu/view.php?seq={seq}")
        except Exception as e:
            print(f"  [warn] 배스킨라빈스 seq={seq}: {e}")
            continue
        soup = BeautifulSoup(html, "html.parser")
        heading = soup.find("h2")
        name = clean(heading.get_text()) if heading else ""
        dl = soup.find("dl")
        if not name or not dl:
            continue
        row = blank_row("배스킨라빈스", name, category)
        pairs = dl.find_all(["dt", "dd"])
        for dt, dd in zip(pairs[0::2], pairs[1::2]):
            column = _BR_LABELS.get(clean(dt.get_text()))
            if column:
                row[column] = num(dd.get_text())
        if has_any_nutrient(row):
            rows.append(row)
        time.sleep(REQUEST_DELAY)
    return _dedupe(rows), "baskinrobbins.csv"


_PAIKDABANG_LABELS = {
    "calorie_kcal": ["칼로리"], "protein_g": ["단백질"], "sugar_g": ["당류"],
    "saturated_fat_g": ["포화지방"], "sodium_mg": ["나트륨"], "caffeine_mg": ["카페인"],
}


def crawl_paikdabang():
    """Every product's nutrition ships inline in the list page markup, inside
    `div.hover` (the hover-reveal detail panel each menu card expands into),
    as `h3.font-bl` (name) + `.ingredient_table` (li pairs of label/value).

    _generic_tables() (the fallback for brands with unknown markup) missed
    this because it only looks at real <table> elements -- this site's
    "table" is a styled <ul>. `div.hover` is not itself a per-product
    container (it also wraps the 3-item "best menu" slider, which duplicates
    3 of the same products), so results are deduped by name after collection.
    """
    pages = {
        "커피": "https://paikdabang.com/menu/menu_coffee/",
        "음료": "https://paikdabang.com/menu/menu_drink/",
        "디저트": "https://paikdabang.com/menu/menu_dessert/",
    }
    rows = []
    for category, url in pages.items():
        try:
            html = fetch(url)
        except Exception as e:
            print(f"  [warn] 빽다방 {category}: {e}")
            continue
        soup = BeautifulSoup(html, "html.parser")
        for hov in soup.select("div.hover"):
            name_el = hov.select_one("h3.font-bl")
            table = hov.select_one(".ingredient_table")
            if not name_el or not table:
                continue
            row = blank_row("빽다방", name_el.get_text(), category)
            for li in table.find_all("li"):
                divs = li.find_all("div")
                if len(divs) != 2:
                    continue
                label, value = clean(divs[0].get_text()), divs[1].get_text()
                for column, keywords in _PAIKDABANG_LABELS.items():
                    if any(kw in label for kw in keywords):
                        row[column] = num(value)
                        break
            if has_any_nutrient(row):
                rows.append(row)
        time.sleep(REQUEST_DELAY)
    return _dedupe(rows), "paikdabang.csv"


COFFEEBEAN_CATEGORIES = {
    "32": "신음료", "13": "에스프레소 음료", "14": "브루드 커피", "18": "티",
    "17": "티 라떼", "12": "아이스 블렌디드(Coffee)", "11": "아이스 블렌디드(Non-Coffee)",
    "26": "커피빈 주스(병음료)", "24": "기타 제조 음료",
}

_COFFEEBEAN_LABELS = {
    "calorie_kcal": ["열량"], "protein_g": ["단백질"], "sugar_g": ["당"],
    "saturated_fat_g": ["포화지방"], "sodium_mg": ["나트륨"], "caffeine_mg": ["카페인"],
}


def crawl_coffeebean():
    """Each product is an <li> holding one `dl.txt` (name) plus several
    `dl.bgN` nutrient blocks -- but reversed from the usual dt/dd order: dt is
    the *value*, dd is the *label* ("dt=4, dd='열량 Kcal'"). _generic_tables()
    assumes real <table> markup and never matched this at all (0 rows).

    9 drink categories, each paginated (?page=N&category=X&category2=1,
    "다음" link disappears on the last page). Food categories (베이커리/케익
    /샌드위치 등) were checked and don't carry this nutrition block, so
    they're intentionally not crawled here.
    """
    rows = []
    for cat_id, category in COFFEEBEAN_CATEGORIES.items():
        page = 1
        while True:
            url = (f"https://www.coffeebeankorea.com/menu/list.asp"
                   f"?page={page}&category={cat_id}&category2=1")
            try:
                html = fetch(url)
            except Exception as e:
                print(f"  [warn] 커피빈 {category} p{page}: {e}")
                break
            soup = BeautifulSoup(html, "html.parser")
            cards = [dl.find_parent("li") for dl in soup.find_all("dl", class_="txt")]
            cards = [c for c in cards if c]
            if not cards:
                break
            for card in cards:
                name_dl = card.find("dl", class_="txt")
                name = clean(name_dl.find("dt").get_text()) if name_dl else ""
                if not name:
                    continue
                row = blank_row("커피빈", name, category)
                for dl in card.find_all("dl"):
                    cls = dl.get("class") or []
                    if "txt" in cls:
                        continue
                    dt, dd = dl.find("dt"), dl.find("dd")
                    if not dt or not dd:
                        continue
                    label = clean(dd.get_text())
                    for column, keywords in _COFFEEBEAN_LABELS.items():
                        if any(kw in label for kw in keywords):
                            row[column] = num(dt.get_text())
                            break
                if has_any_nutrient(row):
                    rows.append(row)
            has_next = soup.find("a", string=lambda s: s and "다음" in s)
            if not has_next:
                break
            page += 1
            time.sleep(REQUEST_DELAY)
        time.sleep(REQUEST_DELAY)
    return _dedupe(rows), "coffeebean.csv"


def crawl_hollys():
    """Each product is a hidden `.menu_info02` panel holding one <table> whose
    <caption> is the product name -- not a header row, which is why
    _generic_tables()/row_from_headers() found 0 usable rows: the table's own
    header row is blank in the name column ('', 칼로리, 당류, ...) and the
    first data column is HOT/ICED, not a product name.

    Survey's URLs were wrong too (brewed.do/beverage.do don't exist -- the
    real category paths are espresso/signature/hollyccino/juice/tea/bakery,
    found via the page's own nav). HOT and ICED are separate nutrition
    profiles for the same drink, so each becomes its own row, suffixed in the
    name to keep them distinguishable.
    """
    pages = {
        "에스프레소": "https://www.hollys.co.kr/menu/espresso.do",
        "라떼·초콜릿·티": "https://www.hollys.co.kr/menu/signature.do",
        "할리치노·빙수": "https://www.hollys.co.kr/menu/hollyccino.do",
        "스무디·주스": "https://www.hollys.co.kr/menu/juice.do",
        "스파클링": "https://www.hollys.co.kr/menu/tea.do",
        "푸드": "https://www.hollys.co.kr/menu/bakery.do",
    }
    rows = []
    for category, url in pages.items():
        try:
            html = fetch(url)
        except Exception as e:
            print(f"  [warn] 할리스 {category}: {e}")
            continue
        soup = BeautifulSoup(html, "html.parser")
        for panel in soup.select(".menu_info02"):
            table = panel.find("table")
            caption = table.find("caption") if table else None
            base_name = clean(caption.get_text()) if caption else ""
            if not base_name:
                continue
            raw_rows = parse_table(table)  # header row: '', 칼로리, 당류, 단백질, 포화지방, 나트륨, 카페인
            for raw in raw_rows:
                variant = None
                row = {c: "" for c in STANDARD_COLUMNS}
                row["restaurant"] = "할리스"
                row["menu_category"] = category
                for key, value in raw.items():
                    if not clean(key):
                        variant = clean(value)  # HOT / ICED
                        continue
                    column = match_nutrient(key)
                    if column:
                        row[column] = num(value)
                row["menu_name"] = f"{base_name} ({variant})" if variant else base_name
                if has_any_nutrient(row):
                    rows.append(row)
        time.sleep(REQUEST_DELAY)
    return _dedupe(rows), "hollys.csv"


def _grid_rows(table):
    """Reconstruct a table's full row grid, forward-filling any cell whose
    rowspan still covers the current row.

    Needed because 도미노's ingredient page nests rowspan two levels deep --
    one pizza's name (rowspan=19) covers every crust-type/size combination it
    comes in, the same shape crawl_lotteria.py hit and fixed by *not* trying
    to reconstruct the grid (it reads each <tr>'s own children, which happen
    to already be positionally correct there). That trick doesn't work here
    because 도미노's data columns genuinely need the carried-forward name to
    know which pizza a row belongs to -- there's no way to get the name
    without filling it in. This does the fill explicitly instead of guessing.
    """
    carry = {}  # column index -> [remaining_rows, text]
    grid = []
    for tr in table.find_all("tr"):
        cells = list(tr.find_all(["td", "th"]))
        row, col, ci = [], 0, 0
        while ci < len(cells) or col in carry:
            if col in carry:
                carry[col][0] -= 1
                row.append(carry[col][1])
                if carry[col][0] <= 0:
                    del carry[col]
            else:
                cell = cells[ci]
                ci += 1
                text = clean(cell.get_text())
                row.append(text)
                span = int(cell.get("rowspan") or 1)
                if span > 1:
                    carry[col] = [span - 1, text]
            col += 1
        grid.append(row)
    return grid


# Column layouts are index-based, not header-matched, because 도미노's tables
# mix a "/150g(1회분) 기준" block with a "/총중량(총용량)" block under
# near-identical header text (both say "열량 (kcal/...)"), and matching by
# label alone can't tell them apart.
#
# The pizza table's per-150g block is the one that's comparable to every other
# brand: 총중량 is a whole L pizza (1,248g / 3,515kcal), which nobody eats as
# one serving, so scoring it against a 275g 맥도날드 버거 made 도미노 look like
# an order-of-magnitude outlier. 150g is 도미노's own declared 1회분.
_DOMINOS_PIZZA_COLS = {  # 16 physical cols (제품명 header has colspan=3)
    "name": 0, "variant": 1, "size": 2,
    "calorie_kcal": 6, "protein_g": 7, "saturated_fat_g": 8,
    "sodium_mg": 9, "sugar_g": 10,
}
# A handful of S-size Subzza rows leave the per-150g block as "-" (they weigh
# under 300g, i.e. already one serving); those fall back to 총중량.
_DOMINOS_PIZZA_TOTAL_COLS = {
    "name": 0, "variant": 1, "size": 2, "weight_g": 3,
    "calorie_kcal": 11, "protein_g": 12, "saturated_fat_g": 13,
    "sodium_mg": 14, "sugar_g": 15,
}
_DOMINOS_DRINK_COLS = {  # 14 cols, no name-group split
    "name": 0, "weight_g": 1,
    "calorie_kcal": 9, "protein_g": 10, "saturated_fat_g": 11,
    "sodium_mg": 12, "sugar_g": 13,
}
# Real 사이드디시 (스파게티/윙/샐러드). 15 cols: a per-1회분 block that only the
# wing rows fill in (1회분 = one wing), then a 총중량 block. 총중량 is the right
# one here -- a 395g 스파게티 or a 7-piece wing order *is* the serving, whereas
# "one 33g wing" isn't a menu item anyone orders.
_DOMINOS_SIDE_COLS = {
    "name": 0, "weight_g": 1,
    "calorie_kcal": 10, "protein_g": 11, "saturated_fat_g": 12,
    "sodium_mg": 13, "sugar_g": 14,
}


def _dominos_rows_from_grid(grid, cols, category, table_index, fallback_cols=None,
                            serving_g=None, default_basis="per_serving"):
    rows = []
    for i, cells in enumerate(grid):
        if i == 0 or len(cells) <= max(cols.values()):
            continue  # header row, or a stray row shorter than expected
        active, basis = cols, default_basis
        if fallback_cols and not num(cells[cols["calorie_kcal"]]):
            active, basis = fallback_cols, "per_total"
        row = {c: "" for c in STANDARD_COLUMNS}
        row["restaurant"] = "도미노피자"
        row["menu_category"] = category
        base = cells[active["name"]]
        variant = clean(cells[active["variant"]]) if "variant" in active else ""
        size = clean(cells[active["size"]]) if "size" in active else ""
        row["menu_name"] = " ".join(p for p in [base, variant, size] if p)
        for column in ("weight_g", "calorie_kcal", "protein_g",
                       "saturated_fat_g", "sodium_mg", "sugar_g"):
            row[column] = num(cells[active[column]]) if column in active else ""
        if serving_g and active is cols:
            row["weight_g"] = serving_g  # the block's own basis, not 총중량
        row["nutrition_basis"] = basis
        if has_any_nutrient(row):
            rows.append(row)
    return rows


def crawl_dominos():
    """/contents/ingredient serves euc-kr (not utf-8, unlike every other
    brand crawled so far) and holds 17 differently-shaped tables rather than
    one: a 466-row pizza table (rowspan-nested), a drinks table, a sides
    table, an ingredient breakdown of what each pizza is *made of*, and
    several allergy/origin-only tables with no nutrition at all.
    _generic_tables() found none of this: it only reads plain <table>s
    without rowspan handling and has no notion of picking one basis block
    over another when both sit under near-identical labels.

    Only tables 4/7/8 are menu items. Deliberately NOT scraped:
      5      하이 프로틴 도우 -- a crust option, per-100g, not an orderable item
      6      콤보 -- calorie only, no other nutrient, so it can never be scored
      9/10/11 도우 / 소스 / 치즈 -- the per-pizza ingredient breakdown. These
              were previously loaded as "사이드" menu items, which is where
              "더블 치즈 엣지L, 2,535kcal" came from: that's the cheese on a
              whole L pizza, not a side dish, and it double-counts the pizza
              rows it is already part of.

    Indices are pinned by position, not searched by header text, since the
    markup gives duplicate-looking headers no reliable way to distinguish by
    string matching alone. Re-verify with inspect_page.py if the page moves.
    """
    html = fetch("https://web.dominos.co.kr/contents/ingredient", encoding="euc-kr")
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")

    rows = []
    rows += _dominos_rows_from_grid(_grid_rows(tables[4]), _DOMINOS_PIZZA_COLS, "피자", 4,
                                    fallback_cols=_DOMINOS_PIZZA_TOTAL_COLS, serving_g=150)
    rows += _dominos_rows_from_grid(_grid_rows(tables[7]), _DOMINOS_SIDE_COLS, "사이드", 7,
                                    default_basis="per_total")
    # 음료's per-150g block is entirely "-", so a 1.5L bottle is genuinely
    # recorded per-container; label it rather than imply per-serving.
    rows += _dominos_rows_from_grid(_grid_rows(tables[8]), _DOMINOS_DRINK_COLS, "음료", 8,
                                    default_basis="per_total")
    return _dedupe(rows), "dominos.csv"


def _dedupe(rows):
    """Same product can appear on several category pages; first one wins."""
    seen = set()
    out = []
    for row in rows:
        key = (row["restaurant"], row["menu_name"])
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


CRAWLERS = {
    # verified in a browser during the survey
    "burgerking": (crawl_burgerking, "MANUAL-ONLY (WAF blocks urllib; see docstring)"),
    "starbucks": (crawl_starbucks, "VERIFIED"),
    "ediya": (crawl_ediya, "VERIFIED"),
    "bhc": (crawl_bhc, "VERIFIED"),
    "kyochon": (crawl_kyochon, "VERIFIED"),
    "pokeallday": (crawl_pokeallday, "VERIFIED"),
    # keyword-probe only -- structure unconfirmed
    "baskinrobbins": (crawl_baskinrobbins, "VERIFIED"),
    "paikdabang": (crawl_paikdabang, "VERIFIED"),
    "coffeebean": (crawl_coffeebean, "VERIFIED"),
    "hollys": (crawl_hollys, "VERIFIED"),
    "dominos": (crawl_dominos, "VERIFIED"),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--brand", help="one of: " + ", ".join(CRAWLERS))
    parser.add_argument("--list", action="store_true", help="show brands and confidence")
    args = parser.parse_args()

    if args.list:
        for slug, (_, confidence) in CRAWLERS.items():
            print(f"  {slug:<16} {confidence}")
        return

    if args.brand:
        if args.brand not in CRAWLERS:
            raise SystemExit(f"unknown brand '{args.brand}'; try --list")
        targets = {args.brand: CRAWLERS[args.brand]}
    else:
        targets = CRAWLERS

    results = {}
    for slug, (fn, confidence) in targets.items():
        print(f"\n=== {slug} ({confidence}) ===")
        try:
            rows, csv_name = fn()
        except Exception as e:
            print(f"  FAILED: {type(e).__name__}: {e}")
            results[slug] = None
            continue
        path = write_csv(rows, csv_name)
        print(f"  {len(rows)} rows -> {path.relative_to(path.parent.parent)}")
        results[slug] = len(rows)

    print("\n--- summary ---")
    for slug, n in results.items():
        status = "FAILED" if n is None else (f"{n} rows" if n else "0 rows (파서 수정 필요)")
        print(f"  {slug:<16} {status}")
    print("\n다음 단계: 0 rows/FAILED 브랜드는 "
          "python scripts/survey/inspect_page.py <url> 로 구조 확인 후 파서 수정")


if __name__ == "__main__":
    main()
