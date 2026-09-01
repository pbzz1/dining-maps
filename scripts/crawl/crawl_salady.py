"""Crawl Salady's official menu detail pages and write data/salady.csv.

(idx, category) pairs are discovered dynamically from the menu list page's
/menu/view_1?idx=&ca_id= links rather than hardcoded, so this keeps working
as Salady adds/removes menu items or categories.
"""
import csv
import re
import time
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent.parent
LIST_URL = "https://salady.com/menu/list_1"
DETAIL_URL = "https://salady.com/menu/view_1?idx={idx}&ca_id={ca}"

CATEGORY_NAMES = {
    "01": "샐러디", "02": "그레인볼", "03": "누들볼", "04": "프로틴박스",
    "0404": "프로틴박스", "05": "랩&샌드위치", "07": "나만의 샐러디",
}


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8")


def num_only(s: str) -> str:
    s = s.strip()
    if not s:
        return ""
    m = re.match(r"^([\d.]+)", s)
    return m.group(1) if m else s


def discover_items() -> list[tuple[str, str]]:
    html = fetch(LIST_URL)
    pairs = re.findall(r"/menu/view_1\?idx=(\d+)&ca_id=(\w+)", html)
    seen = set()
    result = []
    for idx, ca in pairs:
        if idx in seen:
            continue
        seen.add(idx)
        result.append((idx, ca))
    return result


def main():
    pairs = discover_items()
    print(f"discovered {len(pairs)} menu items")

    rows = []
    errors = 0
    for idx, ca in pairs:
        try:
            html = fetch(DETAIL_URL.format(idx=idx, ca=ca))
        except Exception as e:
            errors += 1
            print(f"  [warn] idx={idx}: {e}")
            continue

        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table")
        if not table:
            errors += 1
            continue
        trs = table.find_all("tr")
        if len(trs) < 2:
            errors += 1
            continue
        header = [th.get_text(strip=True) for th in trs[0].find_all(["th", "td"])]
        data = [td.get_text(strip=True) for td in trs[1].find_all(["th", "td"])]
        raw = dict(zip(header, data))

        rows.append(
            {
                "restaurant": "샐러디",
                "menu_name": raw.get("메뉴", ""),
                "menu_category": CATEGORY_NAMES.get(ca, ca),
                "calorie_kcal": num_only(raw.get("열량(kcal)", "")),
                "carb_g": num_only(raw.get("탄수화물(g)", "")),
                "sugar_g": num_only(raw.get("당류(g)", "")),
                "protein_g": num_only(raw.get("단백질(g)", "")),
                "fat_g": num_only(raw.get("지방(g)", "")),
                "saturated_fat_g": num_only(raw.get("포화지방(g)", "")),
                "sodium_mg": num_only(raw.get("나트륨(mg)", "")),
                "menu_item_idx": idx,
            }
        )
        time.sleep(0.2)

    fieldnames = [
        "restaurant", "menu_name", "menu_category", "calorie_kcal", "carb_g", "sugar_g",
        "protein_g", "fat_g", "saturated_fat_g", "sodium_mg", "menu_item_idx",
    ]
    out_path = ROOT / "data" / "salady.csv"
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"wrote {len(rows)} rows to {out_path} ({errors} errors)")


if __name__ == "__main__":
    main()
