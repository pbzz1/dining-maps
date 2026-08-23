"""Compute per-menu-item diet scores using fixed, absolute thresholds
grounded in published guidelines/research (v4 - see docs/diet_score.md
for full citations). Menus are scored on one of two bases:

  meal  -- per-100kcal density of protein/sugar/satfat/sodium (v3 rules).
  drink -- per-serving calorie/sugar/satfat. Protein is not a virtue in a
           coffee, and a 5kcal americano has no meaningful "density", so a
           drink is judged by what one cup actually adds.

Also derives a relative (percentile-based) grade alongside the absolute
one, ranked within the same basis only -- see docs/diet_score.md "절대
기준 vs 상대 기준" for why both exist. Re-run anytime nutrition data
changes; overwrites diet_score."""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.db import connect  # noqa: E402
from app.recommend.goals import is_drink  # noqa: E402

# Only nutrients every brand publishes -- see docs/diet_score.md for why.
REQUIRED_NUTRIENTS = ["calorie", "protein", "sugar", "saturated_fat", "sodium"]
MIN_CALORIE_KCAL = 100  # meals below this: per-100kcal density is a meaningless ratio

# (min, max) total points per basis, for the 0-100 rescale.
POINT_RANGE = {"meal": (-4, 5), "drink": (-3, 4)}

# Relative-grade band widths. B is deliberately the largest band (50%) so
# that, in a real service, most listed menus land on B rather than the
# absolute scale's mostly-D result -- see docs/diet_score.md for the
# rationale and the explicit tradeoff this makes.
RELATIVE_BANDS = {"A": 85, "B": 35, "C": 10}  # percentile >= this -> grade (checked high to low)


# ---- meal basis (per 100kcal) ----

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


# ---- drink basis (per serving) ----

def drink_calorie_points(kcal: float) -> int:
    """kcal per serving. 40 = MFDS/FDA 'low calorie' claim threshold;
    250 ~ a meal's worth of energy in a cup."""
    if kcal <= 40:
        return 2
    if kcal <= 150:
        return 1
    if kcal <= 250:
        return 0
    return -1


def drink_sugar_points(g: float) -> int:
    """g sugar per serving. 25g = WHO ideal free-sugar target for a whole
    day (5%E at 2,000kcal); one cup exceeding that is the clearest fail."""
    if g <= 5:
        return 1
    if g <= 25:
        return 0
    return -1


def drink_saturated_fat_points(g: float) -> int:
    """g saturated fat per serving. 4g ~ 1/3 of AHA 6%E (~13g/day)."""
    if g <= 1:
        return 1
    if g <= 4:
        return 0
    return -1


def meal_points(wide: pd.DataFrame) -> pd.Series:
    per_100kcal = wide[["protein", "sugar", "saturated_fat", "sodium"]].div(wide["calorie"], axis=0) * 100
    return (
        per_100kcal["protein"].apply(protein_points)
        + per_100kcal["sugar"].apply(sugar_points)
        + per_100kcal["saturated_fat"].apply(saturated_fat_points)
        + per_100kcal["sodium"].apply(sodium_points)
    )


def drink_points(wide: pd.DataFrame) -> pd.Series:
    return (
        wide["calorie"].apply(drink_calorie_points)
        + wide["sugar"].apply(drink_sugar_points)
        + wide["saturated_fat"].apply(drink_saturated_fat_points)
    )


SCORERS = {"meal": meal_points, "drink": drink_points}


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
    """Percentile rank among all currently-scored items of the same basis.
    Moves every time this script reruns on a changed catalog -- this is
    the tradeoff for getting a B-heavy, user-friendly distribution."""
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
        kinds = {
            r["id"]: "drink" if is_drink(r["category"], r["name"]) else "meal"
            for r in conn.execute("SELECT id, name, category FROM menu_item").fetchall()
        }
        _score_and_store(conn, rows, kinds)


def score_frame(wide: pd.DataFrame) -> pd.DataFrame:
    """wide: index=menu_item_id, columns=REQUIRED_NUTRIENTS + 'basis'.
    Returns score/percentile/basis/absolute_grade/relative_grade per item."""
    wide = wide[(wide["basis"] == "drink") | (wide["calorie"] >= MIN_CALORIE_KCAL)]
    parts = []
    for basis, scorer in SCORERS.items():
        part = wide[wide["basis"] == basis]
        if part.empty:
            continue
        lo, hi = POINT_RANGE[basis]
        scores = (scorer(part) - lo) / (hi - lo) * 100
        parts.append(pd.DataFrame({
            "score": scores,
            "percentile": scores.rank(pct=True) * 100,  # ranked within the same basis only
            "basis": basis,
        }))
    if not parts:
        return pd.DataFrame(columns=["score", "percentile", "basis", "absolute_grade", "relative_grade"])
    out = pd.concat(parts)
    out["absolute_grade"] = out["score"].apply(absolute_grade_for)
    out["relative_grade"] = out["percentile"].apply(relative_grade_for)
    return out


def _score_and_store(conn, rows, kinds):
    facts = pd.DataFrame(rows, columns=["menu_item_id", "nutrient_name", "value"])
    if facts.empty:
        print("No nutrition facts found; nothing to score.")
        return

    wide = facts.pivot(index="menu_item_id", columns="nutrient_name", values="value")
    wide = wide.dropna(subset=REQUIRED_NUTRIENTS)
    wide["basis"] = wide.index.map(lambda i: kinds.get(i, "meal"))
    out = score_frame(wide)
    if out.empty:
        print("No menu items have all required nutrients; nothing to score.")
        return

    conn.execute("DELETE FROM diet_score")
    conn.cursor().executemany(
        """INSERT INTO diet_score (menu_item_id, score, absolute_grade, relative_grade, percentile, basis)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        [
            (int(idx), round(float(r.score), 2), r.absolute_grade, r.relative_grade, round(float(r.percentile), 2), r.basis)
            for idx, r in out.iterrows()
        ],
    )

    print(f"Scored {len(out)} menu items.")
    print("Absolute grade distribution by basis:")
    print(out.groupby(["basis", "absolute_grade"]).size())
    print("\nRelative grade distribution by basis:")
    print(out.groupby(["basis", "relative_grade"]).size())

    by_restaurant = conn.execute(
        """SELECT r.name AS restaurant, ds.basis, ds.absolute_grade, ds.relative_grade, COUNT(*) AS n
           FROM diet_score ds
           JOIN menu_item mi ON mi.id = ds.menu_item_id
           JOIN restaurant r ON r.id = mi.restaurant_id
           GROUP BY r.name, ds.basis, ds.absolute_grade, ds.relative_grade
           ORDER BY r.name, ds.basis, ds.absolute_grade"""
    ).fetchall()
    print()
    print(pd.DataFrame(by_restaurant).to_string(index=False))


def _selfcheck():
    cols = ["calorie", "protein", "sugar", "saturated_fat", "sodium", "basis"]
    wide = pd.DataFrame(
        [
            [5, 0.5, 0, 0, 5, "drink"],        # americano -> 100, A
            [350, 10, 40, 6, 150, "drink"],    # sweet latte -> -3 -> 0, D
            [5, 0.5, 0, 0, 5, "meal"],         # <100kcal meal -> dropped
            [300, 26, 3, 1.5, 200, "meal"],    # meal stays on v3 rules
        ],
        columns=cols, index=[1, 2, 3, 4],
    )
    out = score_frame(wide)
    assert 3 not in out.index
    assert out.loc[1, "score"] == 100 and out.loc[1, "absolute_grade"] == "A"
    assert out.loc[2, "score"] == 0 and out.loc[2, "absolute_grade"] == "D"
    assert out.loc[4, "basis"] == "meal" and 0 <= out.loc[4, "score"] <= 100
    # percentiles are within-basis: the lone meal is its own 100th percentile
    assert out.loc[4, "percentile"] == 100
    print("selfcheck ok")


if __name__ == "__main__":
    if "--check" in sys.argv:
        _selfcheck()
    else:
        main()
