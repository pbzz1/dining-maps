"""Crawl Lotteria's official nutrition table and write data/lotteria.csv.

The source page renders rowspan/colspan-heavy HTML, but each <tr>'s own
literal <td> children (in document order) are exactly the sequence a browser
would show for that visual row -- rowspan cells from a previous row simply
aren't repeated as children of a later <tr>. So per-row text extraction
plus pattern matching (find the run of weight/calorie/protein/sodium
values) works without needing to reconstruct the full rowspan grid.

Only rows with real per-item numbers are kept; set/combo rows only report a
calorie *range* (varies by side/drink choice) and have no fixed nutrition
value -- see docs/diet_score.md.
"""
import csv
import re
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
URL = "https://www.lotteeatz.com/upload/stg/etc/ria/items.html"


def is_num(s: str) -> bool:
    return bool(re.fullmatch(r"[\d,]+(\.\d+)?", s.strip()))


def is_amount(s: str) -> bool:
    s = s.strip()
    if is_num(s):
        return True
    if re.search(r"\(\s*[\d.]+\s*%\)", s):
        return True
    if "g미만" in s or "g 미만" in s:
        return True
    return False


def parse_amount(s: str) -> str:
    s = s.strip()
    if not s:
        return ""
    if "g미만" in s or "g 미만" in s:
        return "0"
    m = re.match(r"^([\d,]+(?:\.\d+)?)", s)
    return m.group(1).replace(",", "") if m else s


def fetch_rows():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        html = resp.read().decode("utf-8")
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    return table.find_all("tr")


def main():
    trs = fetch_rows()

    current_category = ""
    rows = []
    for tr in trs[1:]:  # skip header row
        cells = [c.get_text(separator=" ", strip=True) for c in tr.find_all(["td", "th"])]
        if not any(cells):
            continue

        # range-type row (세트/콤보): "NNNkcal ~ NNNkcal" appears somewhere -- skip,
        # but still capture the category if this row introduces one.
        range_idx = next((i for i, c in enumerate(cells) if "kcal" in c and "~" in c), None)
        if range_idx is not None:
            leading = cells[:range_idx]
            if len(leading) == 3:
                current_category = leading[0]
            continue

        found_i = None
        for i in range(len(cells) - 3):
            if is_num(cells[i]) and is_num(cells[i + 1]) and is_amount(cells[i + 2]) and is_amount(cells[i + 3]):
                found_i = i
                break
        if found_i is None:
            continue  # header/section-label row we don't recognize -- skip rather than guess

        leading = cells[:found_i]
        weight, calorie, protein, sodium = cells[found_i : found_i + 4]
        sugar = cells[found_i + 4] if len(cells) > found_i + 4 else ""
        satfat = cells[found_i + 5] if len(cells) > found_i + 5 else ""
        caffeine = cells[found_i + 6] if len(cells) > found_i + 6 else ""
        origin = " ".join(cells[found_i + 7 :]) if len(cells) > found_i + 7 else ""

        if len(leading) >= 3:
            current_category = leading[0]
            name = leading[1]
            allergy = " ".join(leading[2:])
        elif len(leading) == 2:
            name, allergy = leading[0], leading[1]
        else:
            name, allergy = (leading[0] if leading else ""), ""

        rows.append(
            {
                "restaurant": "롯데리아",
                "menu_name": name,
                "menu_category": current_category,
                "weight_g": parse_amount(weight),
                "calorie_kcal": parse_amount(calorie),
                "protein_g": parse_amount(protein),
                "sodium_mg": parse_amount(sodium),
                "sugar_g": parse_amount(sugar),
                "saturated_fat_g": parse_amount(satfat),
                "caffeine_mg": parse_amount(caffeine),
                "allergy_info": allergy,
                "origin_info": origin,
            }
        )

    fieldnames = [
        "restaurant", "menu_name", "menu_category", "weight_g", "calorie_kcal", "protein_g",
        "sodium_mg", "sugar_g", "saturated_fat_g", "caffeine_mg", "allergy_info", "origin_info",
    ]
    out_path = ROOT / "data" / "lotteria.csv"
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"wrote {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
