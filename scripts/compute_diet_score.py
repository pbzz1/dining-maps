"""Compute per-menu-item diet scores using fixed, absolute thresholds
grounded in published guidelines/research (v3 - see docs/diet_score.md
for full citations). Also derives a relative (percentile-based) grade
alongside the absolute one -- see docs/diet_score.md "절대 기준 vs 상대
기준" for why both exist. Re-run anytime nutrition data changes;
overwrites diet_score."""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.db import connect  # noqa: E402

# Only nutrients every brand publishes -- see docs/diet_score.md for why.
REQUIRED_NUTRIENTS = ["calorie", "protein", "sugar", "saturated_fat", "sodium"]
MIN_CALORIE_KCAL = 100  # below this, per-100kcal density is a meaningless ratio

MIN_POINTS = -4  # worst case: protein bad(-1) + sugar/satfat/sodium all bad(-1 each)
MAX_POINTS = 5  # best case: protein good(+2) + sugar/satfat/sodium all good(+1 each)

# Relative-grade band widths. B is deliberately the largest band (50%) so
# that, in a real service, most listed menus land on B rather than the
# absolute scale's mostly-D result -- see docs/diet_score.md for the
# rationale and the explicit tradeoff this makes.
RELATIVE_BANDS = {"A": 85, "B": 35, "C": 10}  # percentile >= this -> grade (checked high to low)


def protein_points(v: float) -> int:
    """g protein per 100kcal. Cutoffs: 6.25 = 25%E (MFDS "고단백" claim
    standard); 3.75 = 15%E (Chang 2011, practical AMDR recommendation for
    Koreans); 2.5 = 10%E (~0.8g/kg IBW/day on a ~1200kcal diet, the
    fat-free-mass-preserving threshold found in Lee et al. 2004)."""
    if v >= 6.25:
        return 2
    if v >= 3.75:
        return 1
    if v >= 2.5:
        return 0
    return -1


def sugar_points(v: float) -> int:
    """g sugar per 100kcal. Cutoffs: 1.25 = 5%E (WHO 2015 ideal target);
    2.5 = 10%E (WHO/US/Korean free-sugar upper limit)."""
    if v <= 1.25:
        return 1
    if v <= 2.5:
        return 0
    return -1


def saturated_fat_points(v: float) -> int:
    """g saturated fat per 100kcal. Cutoffs: 0.6 = ~5.5%E (AHA/ACC
    recommendation); 0.8 = ~7%E (Korean dyslipidemia treatment guideline
    upper limit)."""
    if v <= 0.6:
        return 1
    if v <= 0.8:
        return 0
    return -1


def sodium_points(v: float) -> int:
    """mg sodium per 100kcal, proportional to a 2,000kcal/day reference
    intake (same convention as %DV on nutrition labels). Cutoffs:
    75 = 1,500mg/day (AHA ideal target); 100 = 2,000mg/day (WHO/US upper
    limit)."""
    if v <= 75:
        return 1
    if v <= 100:
        return 0
    return -1


def absolute_grade_for(score: float) -> str:
    """Fixed WHO/논문-derived cutoffs. Doesn't move as the catalog changes."""
    if score >= 80:
        return "A"
    if score >= 60:
        return "B"
    if score >= 40:
        return "C"
    return "D"


def relative_grade_for(percentile: float) -> str:
    """Percentile rank among all currently-scored items. Moves every time
    this script reruns on a changed catalog -- this is the tradeoff for
    getting a B-heavy, user-friendly distribution."""
    if percentile >= RELATIVE_BANDS["A"]:
        return "A"
    if percentile >= RELATIVE_BANDS["B"]:
        return "B"
    if percentile >= RELATIVE_BANDS["C"]:
        return "C"
    return "D"


def main():
    with connect() as conn:
        rows = conn.execute(
            """SELECT mi.id AS menu_item_id, nf.nutrient_name, nf.value
               FROM menu_item mi
               JOIN nutrition_fact nf ON nf.menu_item_id = mi.id
               WHERE nf.nutrient_name = ANY(%s)""",
            (REQUIRED_NUTRIENTS,),
        ).fetchall()
        _score_and_store(conn, rows)


def _score_and_store(conn, rows):
    facts = pd.DataFrame(rows, columns=["menu_item_id", "nutrient_name", "value"])
    if facts.empty:
        print("No nutrition facts found; nothing to score.")
        return

    wide = facts.pivot(index="menu_item_id", columns="nutrient_name", values="value")
    wide = wide.dropna(subset=REQUIRED_NUTRIENTS)
    wide = wide[wide["calorie"] >= MIN_CALORIE_KCAL]

    if wide.empty:
        print("No menu items have all required nutrients; nothing to score.")
        return

    per_100kcal = pd.DataFrame(index=wide.index)
    for nutrient in ["protein", "sugar", "saturated_fat", "sodium"]:
        per_100kcal[nutrient] = wide[nutrient] / wide["calorie"] * 100

    points = pd.DataFrame(index=wide.index)
    points["protein"] = per_100kcal["protein"].apply(protein_points)
    points["sugar"] = per_100kcal["sugar"].apply(sugar_points)
    points["saturated_fat"] = per_100kcal["saturated_fat"].apply(saturated_fat_points)
    points["sodium"] = per_100kcal["sodium"].apply(sodium_points)

    total_points = points.sum(axis=1)
    scores = (total_points - MIN_POINTS) / (MAX_POINTS - MIN_POINTS) * 100
    percentiles = scores.rank(pct=True) * 100

    absolute_grades = scores.apply(absolute_grade_for)
    relative_grades = percentiles.apply(relative_grade_for)

    conn.execute("DELETE FROM diet_score")
    conn.cursor().executemany(
        """INSERT INTO diet_score (menu_item_id, score, absolute_grade, relative_grade, percentile)
           VALUES (%s, %s, %s, %s, %s)""",
        [
            (int(idx), round(float(s), 2), ag, rg, round(float(p), 2))
            for idx, s, ag, rg, p in zip(scores.index, scores, absolute_grades, relative_grades, percentiles)
        ],
    )

    print(f"Scored {len(scores)} menu items.")
    print("Absolute grade distribution:")
    print(absolute_grades.value_counts().sort_index())
    print("\nRelative grade distribution:")
    print(relative_grades.value_counts().sort_index())

    by_restaurant = conn.execute(
        """SELECT r.name AS restaurant, ds.absolute_grade, ds.relative_grade, COUNT(*) AS n
           FROM diet_score ds
           JOIN menu_item mi ON mi.id = ds.menu_item_id
           JOIN restaurant r ON r.id = mi.restaurant_id
           GROUP BY r.name, ds.absolute_grade, ds.relative_grade
           ORDER BY r.name, ds.absolute_grade"""
    ).fetchall()
    print()
    print(pd.DataFrame(by_restaurant).to_string(index=False))


if __name__ == "__main__":
    main()
