import { useEffect, useState } from "react";
import { fetchRestaurants, fetchDietGrade } from "../api";
import { GradeBadges, GradeLegend } from "./GradeBadges";

export default function RestaurantList({ onSelect }) {
  const [restaurants, setRestaurants] = useState([]);
  const [grades, setGrades] = useState({});
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    fetchRestaurants()
      .then((list) => {
        if (cancelled) return;
        setRestaurants(list);
        // Grade badges are best-effort: a card still renders if its grade fails.
        list.forEach((r) =>
          fetchDietGrade(r.id)
            .then((g) => !cancelled && setGrades((prev) => ({ ...prev, [r.id]: g })))
            .catch(() => {})
        );
      })
      .catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) return <p className="error">매장 목록을 불러오지 못했습니다: {error}</p>;

  return (
    <section>
      <h2>매장 선택</h2>
      <GradeLegend />
      <div className="card-grid">
        {restaurants.length === 0 && <p className="loading">불러오는 중...</p>}
        {restaurants.map((r) => {
          const g = grades[r.id];
          return (
            <div key={r.id} className="restaurant-card" onClick={() => onSelect(r)}>
              <div className="name">{r.name}</div>
              <div className="card-grade-slot">
                {g?.absolute_grade && (
                  <>
                    <GradeBadges absolute={g.absolute_grade} relative={g.relative_grade} />
                    <span className="count">
                      다이어트 메뉴 {Math.round(g.good_menu_ratio * 100)}%
                    </span>
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
