"""Crawl McDonald's Korea official nutrition API and write data/mcdonalds.csv.
Only single-serve menu groups are kept (sets/combos vary by side choice and
have no fixed nutrition value -- see docs/diet_score.md)."""
import csv
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
API_URL = "https://www.mcdonalds.co.kr/api/v1/kor/product/nutrition"
SINGLE_GROUPS = {"단품", "버거", "디저트", "스낵 & 사이드", "음료", "해피밀(옵션)"}


def parse_nutrition_facts(raw: str) -> dict:
    out = {}
    if not raw or raw == "-":
        return out
    for part in raw.split(","):
        if ";" not in part:
            continue
        k, v = part.split(";", 1)
        out[k.strip()] = v.strip()
    return out


def num(v):
    if v is None:
        return ""
    m = re.match(r"([\d.]+)", v.replace(",", ""))
    return m.group(1) if m else ""


def fetch():
    req = urllib.request.Request(API_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        import json

        return json.loads(resp.read().decode("utf-8"))["resultObject"]["list"]


def main():
    items = fetch()

    rows = []
    for i in items:
        if i["menuGroup"] not in SINGLE_GROUPS:
            continue
        nf = parse_nutrition_facts(i["nutritionFacts"])
        if not nf:
            continue
        rows.append(
            {
                "restaurant": "맥도날드",
                "menu_name": i["menuName"],
                "menu_group": i["menuGroup"],
                "price_krw": i["price"] or "",
                "weight_g": num(nf.get("중량")),
                "calorie_kcal": num(nf.get("열량")),
                "protein_g": num(nf.get("단백질")),
                "sugar_g": num(nf.get("당")),
                "saturated_fat_g": num(nf.get("포화지방")),
                "sodium_mg": num(nf.get("나트륨")),
                "caffeine_mg": num(nf.get("카페인")),
                "allergy_info": i["allergyInfo"],
            }
        )

    fieldnames = [
        "restaurant", "menu_name", "menu_group", "price_krw", "weight_g", "calorie_kcal",
        "protein_g", "sugar_g", "saturated_fat_g", "sodium_mg", "caffeine_mg", "allergy_info",
    ]
    out_path = ROOT / "data" / "mcdonalds.csv"
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"wrote {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
