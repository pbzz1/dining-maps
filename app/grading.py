"""브랜드 등급 계산. restaurants·stores 라우터가 같이 쓴다 -- 자세한 근거는
docs/diet_score.md."""


def absolute_grade_for(score: float) -> str:
    """Fixed WHO/논문-derived cutoffs -- see docs/diet_score.md."""
    if score >= 80:
        return "A"
    if score >= 60:
        return "B"
    if score >= 40:
        return "C"
    return "D"


# Brand-level relative grade: rank every scored brand by avg menu score and
# cut the ranking into even quarters -> A/B/C/D. "A" literally means "top 25%
# of brands in the DB right now", so it moves as brands are added.
BRAND_BANDS = ((0.25, "A"), (0.5, "B"), (0.75, "C"), (1.0, "D"))

GRADE_RANK = {"A": 0, "B": 1, "C": 2, "D": 3}  # lower is better, for "at least this grade" filtering


def brand_relative_grades(conn) -> dict[int, str]:
    """restaurant_id -> A/B/C/D by rank of avg diet score among all scored brands."""
    rows = conn.execute(
        """SELECT mi.restaurant_id, AVG(ds.score) AS avg_score
           FROM diet_score ds JOIN menu_item mi ON mi.id = ds.menu_item_id
           GROUP BY mi.restaurant_id ORDER BY avg_score DESC, mi.restaurant_id"""
    ).fetchall()
    n = len(rows)
    return {r["restaurant_id"]: next(g for cut, g in BRAND_BANDS if (i + 1) / n <= cut + 1e-9) for i, r in enumerate(rows)}
