"""Crawl Subway Korea's official sandwich detail pages and write data/subway.csv.

Sandwich IDs are discovered dynamically from the list page's
data-menuitemidx attributes rather than hardcoded, so this keeps working as
Subway adds/removes menu items.
"""
import csv
import re
import time
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent.parent
LIST_URL = "https://www.subway.co.kr/menuList/sandwich"
DETAIL_URL = "https://www.subway.co.kr/menuView/sandwich?menuItemIdx={idx}"


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


def discover_ids() -> list[str]:
    html = fetch(LIST_URL)
    return sorted(set(re.findall(r'data-menuitemidx="(\d+)"', html)), key=int)


def main():
    ids = discover_ids()
    print(f"discovered {len(ids)} sandwich ids")

    rows = []
    errors = 0
    for idx in ids:
        try:
            html = fetch(DETAIL_URL.format(idx=idx))
        except Exception as e:
            errors += 1
            print(f"  [warn] idx={idx}: {e}")
            continue

        soup = BeautifulSoup(html, "html.parser")
        name_tag = soup.select_one(".view_tit h2") or soup.select_one("h2")
        name = name_tag.get_text(strip=True) if name_tag else ""
        eng_tag = soup.select_one(".view_tit p")
        name_en = eng_tag.get_text(strip=True) if eng_tag else ""

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
                "restaurant": "서브웨이",
                "menu_name": name,
                "menu_name_en": name_en,
                "menu_category": "샌드위치",
                "weight_g": num_only(raw.get("중량(g)", "")),
                "calorie_kcal": num_only(raw.get("열량(kcal)", "")),
                "protein_g": num_only(raw.get("단백질(g)", "")),
                "sugar_g": num_only(raw.get("당류(g)", "")),
                "saturated_fat_g": num_only(raw.get("포화지방(g)", "")),
                "sodium_mg": num_only(raw.get("나트륨(mg)", "")),
                "menu_item_idx": idx,
            }
        )
        time.sleep(0.2)

    fieldnames = [
        "restaurant", "menu_name", "menu_name_en", "menu_category", "weight_g", "calorie_kcal",
        "protein_g", "sugar_g", "saturated_fat_g", "sodium_mg", "menu_item_idx",
    ]
    out_path = ROOT / "data" / "subway.csv"
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"wrote {len(rows)} rows to {out_path} ({errors} errors)")


if __name__ == "__main__":
    main()
