"""2026-09 재조사(docs/crawl_handoff.md)로 확정된 신규 브랜드 크롤러 모음.

사용법: python scripts/crawl_new_brands.py [brand ...]
brand 생략 시 전체. 브랜드명: papajohns mrpizza megacoffee sulbing eggdrop
compose paulbassett tlj parisbaguette hsd

모든 URL·셀렉터는 2026-09-01 드라이런으로 검증된 값 (docs/crawl_handoff.md 참조).
"""
import re
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from crawl_common import (fetch, num, clean, write_csv, match_nutrient,
                          extract_nutrients, has_any_nutrient)
from bs4 import BeautifulSoup

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DELAY = 0.35


def soup_of(url, **kw):
    time.sleep(DELAY)
    return BeautifulSoup(fetch(url, **kw), "html.parser")


def base_row(restaurant, name, category=""):
    return {"restaurant": restaurant, "menu_name": clean(name),
            "menu_category": category, "weight_g": "", "price_krw": "",
            "calorie_kcal": "", "protein_g": "", "sugar_g": "",
            "saturated_fat_g": "", "sodium_mg": "", "caffeine_mg": "",
            "nutrition_basis": ""}


def report(brand, rows, path):
    kcals = [float(r["calorie_kcal"]) for r in rows if r.get("calorie_kcal")]
    lo = min(kcals) if kcals else "-"
    hi = max(kcals) if kcals else "-"
    print(f"[{brand}] {len(rows)} rows -> {path.name} (kcal {lo}~{hi})", flush=True)


# ---------------------------------------------------------------- papajohns
def crawl_papajohns():
    """네트워크 불필요: data/papajohns_nutrition_raw.tsv(모달 캡처본) 파싱."""
    raw = (DATA_DIR / "papajohns_nutrition_raw.tsv").read_text(encoding="utf-8")
    rows, section, carry = [], "", ""
    for line in raw.splitlines():
        if line.startswith("#") and not line.startswith("###"):
            continue
        if line.startswith("###"):
            section = re.sub(r"[#()0-9행 ]", "", line)
            carry = ""
            continue
        cols = line.split("\t")
        if len(cols) < 6 or cols[0] in ("제품명",):
            continue
        if section == "피자":
            if cols[0] in ("R", "L", "F", "P"):
                cols = [carry] + cols
            if len(cols) != 11:
                continue
            carry = cols[0]
            r = base_row("파파존스", f"{cols[0]}({cols[1]} {cols[2]})", "피자")
            r["weight_g"] = num(cols[5])
            vals = cols[6:11]
        elif section == "사이드":
            if len(cols) != 8:
                continue
            r = base_row("파파존스", cols[0], "사이드")
            r["weight_g"] = num(cols[2])
            vals = cols[3:8]
        else:  # 음료 / 소스
            if len(cols) != 7:
                continue
            r = base_row("파파존스", cols[0], section)
            r["weight_g"] = num(cols[1])
            vals = cols[2:7]
        for col, v in zip(("calorie_kcal", "sugar_g", "protein_g",
                           "saturated_fat_g", "sodium_mg"), vals):
            r[col] = num(v)
        rows.append(r)
    path = write_csv(rows, "papajohns.csv")
    report("papajohns", rows, path)


# ------------------------------------------------------------------ mrpizza
def grid_rows(table):
    """rowspan을 펼친 tbody 그리드 (도미노와 같은 유형)."""
    out, spans = [], {}
    for tr in table.find_all("tr"):
        if tr.find("th") and not tr.find("td"):
            continue
        row, col, cells = [], 0, iter(tr.find_all("td"))
        while True:
            if col in spans:
                txt, rem = spans[col]
                row.append(txt)
                if rem <= 1:
                    del spans[col]
                else:
                    spans[col] = (txt, rem - 1)
                col += 1
                continue
            c = next(cells, None)
            if c is None:
                break
            txt = clean(c.get_text())
            rs = int(c.get("rowspan") or 1)
            row.append(txt)
            if rs > 1:
                spans[col] = (txt, rs - 1)
            col += 1
        # 행 끝에 남은 rowspan 열 채우기
        while col in spans:
            txt, rem = spans[col]
            row.append(txt)
            if rem <= 1:
                del spans[col]
            else:
                spans[col] = (txt, rem - 1)
            col += 1
        if row:
            out.append(row)
    return out


def crawl_mrpizza():
    soup = soup_of("https://www.mrpizza.co.kr/sh_page/menuinfo.php?type=2")
    rows = []
    for table in soup.find_all("table"):
        heads = [clean(th.get_text()) for th in table.find_all("th")]
        if "열량(kcal)" not in " ".join(heads):
            continue
        for g in grid_rows(table):
            if len(g) != 12 or not num(g[7]):
                continue
            r = base_row("미스터피자", g[2], "피자")
            r["weight_g"] = num(g[6])
            for col, v in zip(("calorie_kcal", "sugar_g", "protein_g",
                               "saturated_fat_g", "sodium_mg"), g[7:12]):
                r[col] = num(v)
            rows.append(r)
    path = write_csv(rows, "mrpizza.csv")
    report("mrpizza", rows, path)


# --------------------------------------------------------------- megacoffee
def crawl_megacoffee():
    cats = [("1", "1", "음료"), ("2", "2", "푸드"), ("3", "3", "상품")]
    rows, seen = [], set()
    for c1, c2, cname in cats:
        page, last = 1, 1
        while page <= last:
            url = ("https://mega-mgccoffee.com/menu/menu.php?"
                   f"page={page}&menu_category1={c1}&menu_category2={c2}"
                   "&category=&list_checkbox_all=all")
            soup = soup_of(url)
            m = soup.select_one("a.board_page_last")
            if m and m.get("data-page"):
                last = int(m["data-page"])
            for li in soup.select("#menu_list > li"):
                b = li.select_one(".cont_text_title b")
                if not b:
                    continue
                name = clean(b.get_text())
                # HOT/ICE 라벨 병기 -- 같은 메뉴가 온도별 별도 항목이라 이름만으론 충돌
                temps = {clean(l.get_text()) for l in
                         li.select(".cont_gallery_list_label")} & {"HOT", "ICE"}
                if temps:
                    name = f"{name}({'/'.join(sorted(temps))})"
                text = li.get_text(" ")
                kcal = re.search(r"1회 제공량\s*([\d.,]+)\s*kcal", text)
                key = (name, kcal.group(1) if kcal else "")
                if key in seen:
                    continue
                seen.add(key)
                r = base_row("메가커피", name, cname)
                if kcal:
                    r["calorie_kcal"] = num(kcal.group(1))
                for nli in li.select(".cont_list_small li"):
                    t = clean(nli.get_text())
                    col = match_nutrient(t)
                    if col and not r[col]:
                        r[col] = num(t)
                if has_any_nutrient(r):
                    rows.append(r)
            page += 1
    path = write_csv(rows, "megacoffee.csv")
    report("megacoffee", rows, path)


# ------------------------------------------------------------------ sulbing
def crawl_sulbing():
    rows = []
    for t in ("설빙", "음료", "사이드"):
        listing = fetch("https://sulbing.com/menu/?type=" + urllib.parse.quote(t))
        ids = sorted(set(re.findall(r"menu_view\.php\?menu=(\d+)", listing)))
        for mid in ids:
            soup = soup_of(f"https://sulbing.com/menu/menu_view.php?menu={mid}")
            title = soup.select_one(".productTitle")
            if not title:
                continue
            r = base_row("설빙", title.get_text(), t)
            for li in soup.select("ul.infomation li"):
                head = li.select_one(".title")
                con = li.select_one(".con")
                if head and con and "영양" in head.get_text():
                    r.update({k: v for k, v in
                              extract_nutrients(con.get_text()).items() if v})
            if has_any_nutrient(r):
                rows.append(r)
    path = write_csv(rows, "sulbing.csv")
    report("sulbing", rows, path)


# ------------------------------------------------------------------ eggdrop
EGGDROP_COLS = {"중량": "weight_g", "열량": "calorie_kcal", "당": "sugar_g",
                "단백질": "protein_g", "포화지방": "saturated_fat_g",
                "나트륨": "sodium_mg", "카페인": "caffeine_mg"}


def crawl_eggdrop():
    cats = ["NEW", "SANDWICH", "BAGEL", "BRUNCH", "SET MENU", "SIDE",
            "DRINK, COFFEE"]
    rows, seen = [], set()
    for cat in cats:
        listing = fetch("https://eggdrop.com/menu/list.php?category="
                        + urllib.parse.quote(cat))
        for seq in sorted(set(re.findall(r"view\.php\?seq=(\d+)", listing))):
            if seq in seen:
                continue
            seen.add(seq)
            soup = soup_of(f"https://eggdrop.com/menu/view.php?seq={seq}")
            header = soup.select_one("header h2")
            if not header:
                continue
            kor = header.find_next_sibling("p")
            name = clean(kor.get_text()) if kor and clean(kor.get_text()) \
                else clean(header.get_text())
            table = next((tb for tb in soup.find_all("table")
                          if "나트륨" in tb.get_text()), None)
            if table is None:
                continue
            heads = [clean(th.get_text()) for th in table.select("thead th")]
            vals = [clean(td.get_text())
                    for td in table.select("tbody td")]
            # thead 첫 칸이 '구분'류 라벨이면 값 개수에 맞춰 우측 정렬
            if len(heads) > len(vals):
                heads = heads[len(heads) - len(vals):]
            r = base_row("에그드랍", name, cat)
            for h, v in zip(heads, vals):
                col = EGGDROP_COLS.get(h) or match_nutrient(h)
                if col and not r[col]:
                    r[col] = num(v)
            if has_any_nutrient(r):
                rows.append(r)
    path = write_csv(rows, "eggdrop.csv")
    report("eggdrop", rows, path)


# ------------------------------------------------------------------ compose
COMPOSE_CATS = [("303364", "커피·콜드브루"), ("303365", "베버리지"),
                ("303366", "프라페·스무디"), ("303367", "밀크쉐이크"),
                ("303368", "에이드·주스"), ("303369", "티"),
                ("308857", "푸드·디저트"), ("303371", "아이스크림")]


def crawl_compose():
    rows, seen = [], set()
    for srl, cname in COMPOSE_CATS:
        page, items = 1, set()
        while page <= 6:
            listing = fetch("https://composecoffee.com/index.php?mid=compose"
                            f"&act=dispCafemenuGalleryList&category_srl={srl}"
                            f"&page={page}")
            found = set(re.findall(r"item_srl=(\d+)", listing))
            if not (found - items):
                break
            items |= found
            page += 1
        for item in sorted(items):
            if item in seen:
                continue
            seen.add(item)
            soup = soup_of("https://composecoffee.com/index.php?mid=compose"
                           f"&act=dispCafemenuGalleryItem&category_srl={srl}"
                           f"&item_srl={item}")
            title = soup.select_one("h1.cafemenu-detail-title")
            if not title:
                continue
            r = base_row("컴포즈커피", title.get_text(), cname)
            for it in soup.select(".cafemenu-nutrition-item"):
                lab = it.select_one(".cafemenu-nutrition-label")
                val = it.select_one(".cafemenu-nutrition-value")
                if not (lab and val):
                    continue
                col = match_nutrient(lab.get_text())
                if col and not r[col]:
                    r[col] = num(val.get_text())
            if has_any_nutrient(r):
                rows.append(r)
    path = write_csv(rows, "composecoffee.csv")
    report("compose", rows, path)


# -------------------------------------------------------------- paulbassett
PB_CATS = {"A": "커피", "B": "베버리지", "C": "아이스크림", "D": "푸드",
           "E": "상품"}


def crawl_paulbassett():
    base = "https://www.baristapaulbassett.co.kr"
    rows, seen = [], set()
    for cid in "ABCDE":
        soup = soup_of(f"{base}/menu/List.pb?cid1={cid}")
        for el in soup.select('[onclick*="goView"]'):
            m = re.search(r"goView\('(PB\d+)'\)", el.get("onclick") or "")
            if not m or m.group(1) in seen:
                continue
            dpid = m.group(1)
            # 이름: a 내부 div.txtArea (span.sTxt는 영문 부제라 제거)
            txt = el.select_one("div.txtArea")
            if txt is None:
                continue
            for span in txt.find_all("span"):
                span.extract()
            name = clean(txt.get_text())
            if not name:
                continue
            seen.add(dpid)
            detail = soup_of(f"{base}/menu/View.pb?dpid={dpid}")
            r = base_row("폴바셋", name, PB_CATS[cid])
            for li in detail.select("li"):
                tit = li.select_one("span.tit")
                val = li.select_one("span.num")
                if not (tit and val):
                    continue
                col = match_nutrient(tit.get_text())
                if col and not r[col]:
                    r[col] = num(val.get_text())
            if has_any_nutrient(r):
                rows.append(r)
    path = write_csv(rows, "paulbassett.csv")
    report("paulbassett", rows, path)


# ---------------------------------------------------------------------- tlj
TLJ_REFS = [("2", "빵"), ("3", "케이크"), ("4", "음료"), ("5", "디저트·스낵"),
            ("39", "델리")]
TLJ_NUTRI = [("calorie_kcal", r"열량\(kcal\)\s*([\d.,]+)"),
             ("sugar_g", r"당류\(g/%\)\s*([\d.,]+)"),
             ("protein_g", r"단백질\(g/%\)\s*([\d.,]+)"),
             ("saturated_fat_g", r"포화지방\(g/%\)\s*([\d.,]+)"),
             ("sodium_mg", r"나트륨\(mg/%\)\s*([\d.,]+)")]


def crawl_tlj():
    rows, seen = [], set()
    for ref, cname in TLJ_REFS:
        listing = fetch(f"https://www.tlj.co.kr/product/list.asp?ref={ref}&page=30",
                        encoding="euc-kr")
        for pid in sorted(set(re.findall(r"viewDetail\('(\d+)'\)", listing))):
            if pid in seen:
                continue
            seen.add(pid)
            soup = soup_of(f"https://www.tlj.co.kr/product/detail.asp?prod_num={pid}",
                           encoding="euc-kr")
            og = soup.select_one('meta[property="og:title"]')
            name = clean((og["content"] if og else "").split("_")[0])
            table = soup.select_one("div.table_nutrition")
            if not (name and table):
                continue
            text = clean(table.get_text(" "))
            r = base_row("뚜레쥬르", name, cname)
            w = re.search(r"총중량\(g\)\s*([\d.,]+)", text)
            if w:
                r["weight_g"] = num(w.group(1))
            for col, pat in TLJ_NUTRI:
                m = re.search(pat, text)
                if m:
                    r[col] = num(m.group(1))
            if has_any_nutrient(r):
                rows.append(r)
    path = write_csv(rows, "tlj.csv")
    report("tlj", rows, path)


# -------------------------------------------------------------- parisbaguette
PB_NUTRI = {"칼로리": "calorie_kcal", "나트륨": "sodium_mg", "당류": "sugar_g",
            "포화지방": "saturated_fat_g", "단백질": "protein_g"}


def crawl_parisbaguette():
    sitemap = fetch("https://www.paris.co.kr/product-sitemap.xml")
    urls = re.findall(r"<loc>(https://www\.paris\.co\.kr/product/[^<]+)</loc>",
                      sitemap)
    rows = []
    for url in urls:
        try:
            soup = soup_of(url)
        except Exception as e:
            print(f"  skip {url[-40:]}: {e}", flush=True)
            continue
        name_el = soup.select_one("h1.product-name")
        nutri = soup.select_one(".product-nutrition .product-info-group-description")
        if not (name_el and nutri):
            continue
        text = clean(nutri.get_text(" "))
        r = base_row("파리바게뜨", name_el.get_text())
        w = re.search(r"총 내용량\s*:\s*([\d.,]+)\s*g", text)
        if w:
            r["weight_g"] = num(w.group(1))
        for m in re.finditer(r"(칼로리|나트륨|당류|포화지방|단백질)"
                             r"\((?:kcal|mg|g)\)\s*:\s*([\d.,]+)", text):
            col = PB_NUTRI[m.group(1)]
            if not r[col]:
                r[col] = num(m.group(2))
        if has_any_nutrient(r):
            rows.append(r)
    path = write_csv(rows, "parisbaguette.csv")
    report("parisbaguette", rows, path)


# ---------------------------------------------------------------------- hsd
def crawl_hsd():
    """열량·가격만 있는 partial 브랜드. 인덱스는 data/hsd_menu_index_raw.tsv."""
    rows = []
    for line in (DATA_DIR / "hsd_menu_index_raw.tsv").read_text(
            encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        c1, c2, cname, idx, label = line.split("\t")
        name = re.sub(r"\s*가격:.*$", "", label)
        price = num(re.search(r"가격:\s*([\d,]+)원", label).group(1)
                    if "가격:" in label else "")
        try:
            html = fetch(f"https://www.hsd.co.kr/menu/menu_view/{idx}"
                         f"?cate1={c1}&cate2={c2}")
            time.sleep(DELAY)
        except Exception as e:
            print(f"  skip hsd idx={idx}: {e}", flush=True)
            continue
        kcal = re.search(r"<span>([\d.,]+)</span>\s*Kcal", html)
        r = base_row("한솥도시락", name, cname)
        r["price_krw"] = price
        if kcal:
            r["calorie_kcal"] = num(kcal.group(1))
        if has_any_nutrient(r):
            rows.append(r)
    path = write_csv(rows, "hsd.csv")
    report("hsd", rows, path)


CRAWLERS = {"papajohns": crawl_papajohns, "mrpizza": crawl_mrpizza,
            "megacoffee": crawl_megacoffee, "sulbing": crawl_sulbing,
            "eggdrop": crawl_eggdrop, "compose": crawl_compose,
            "paulbassett": crawl_paulbassett, "tlj": crawl_tlj,
            "parisbaguette": crawl_parisbaguette, "hsd": crawl_hsd}

if __name__ == "__main__":
    targets = sys.argv[1:] or list(CRAWLERS)
    for t in targets:
        try:
            CRAWLERS[t]()
        except Exception as e:
            print(f"[{t}] FAILED: {type(e).__name__}: {e}", flush=True)
