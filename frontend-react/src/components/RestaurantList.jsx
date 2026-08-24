import { useEffect, useState } from "react";
import { fetchRestaurants } from "../api";
import { GradeBadges, GradeLegend } from "./GradeBadges";
import BrandAvatar from "./BrandAvatar";
import { BRAND_SLUGS, ALL_GRADES, GRADE_CLASS, gradeTint, gradeBorder } from "../constants";

export default function RestaurantList({ onSelect }) {
  const [restaurants, setRestaurants] = useState([]);
  const [error, setError] = useState(null);
  // Showing both grades at once on every card reads as noise -- default to
  // the one people actually compare stores by, let them switch to the fixed
  // WHO/논문 one when they want that instead. Tiers below group by this same
  // grade, so switching the toggle re-sorts stores into different rows too.
  const [gradeMode, setGradeMode] = useState("relative");

  useEffect(() => {
    let cancelled = false;
    // Grades come inlined on /api/restaurants -- one request for the whole page.
    fetchRestaurants()
      .then((list) => !cancelled && setRestaurants(list))
      .catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) return <p className="error">매장 목록을 불러오지 못했습니다: {error}</p>;

  const gradeOf = (r) => (gradeMode === "absolute" ? r.absolute_grade : r.relative_grade);
  const tiers = ALL_GRADES.map((grade) => ({
    grade,
    items: restaurants.filter((r) => gradeOf(r) === grade),
  })).filter((t) => t.items.length > 0);
  const ungraded = restaurants.filter((r) => !r.absolute_grade);

  return (
    <section>
      <h2>매장 선택</h2>
      <div className="grade-mode-toggle" role="group" aria-label="등급 기준 선택">
        <button
          type="button"
          className={gradeMode === "relative" ? "active" : ""}
          onClick={() => setGradeMode("relative")}
        >
          상대 기준
        </button>
        <button
          type="button"
          className={gradeMode === "absolute" ? "active" : ""}
          onClick={() => setGradeMode("absolute")}
        >
          절대 기준
        </button>
      </div>
      <GradeLegend mode={gradeMode} />
      {restaurants.length === 0 && <p className="loading">불러오는 중...</p>}
      {tiers.map(({ grade, items }) => (
        <div key={grade} className="tier-row">
          <div className={`tier-label ${GRADE_CLASS[grade]}`}>{grade}</div>
          <div className="card-grid">
            {items.map((r) => (
              <div
                key={r.id}
                className="restaurant-card"
                style={{ background: gradeTint(grade), borderColor: gradeBorder(grade) }}
                onClick={() => onSelect(r)}
              >
                <BrandAvatar name={r.name} slug={BRAND_SLUGS[r.name]} />
                <div className="name">{r.name}</div>
                <div className="card-grade-slot">
                  <GradeBadges absolute={r.absolute_grade} relative={r.relative_grade} mode={gradeMode} />
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
      {ungraded.length > 0 && (
        <div className="tier-row">
          <div className="tier-label tier-label-none">-</div>
          <div className="card-grid">
            {ungraded.map((r) => (
              <div key={r.id} className="restaurant-card" onClick={() => onSelect(r)}>
                <BrandAvatar name={r.name} slug={BRAND_SLUGS[r.name]} />
                <div className="name">{r.name}</div>
                <div className="card-grade-slot">
                  <span className="count">영양정보 부족 (등급 산출 불가)</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
