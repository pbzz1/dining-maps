import { useEffect, useState } from "react";
import { fetchRestaurants } from "../api";
import { GradeBadges, GradeLegend } from "./GradeBadges";

export default function RestaurantList({ onSelect }) {
  const [restaurants, setRestaurants] = useState([]);
  const [error, setError] = useState(null);

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

  return (
    <section>
      <h2>매장 선택</h2>
      <GradeLegend />
      <div className="card-grid">
        {restaurants.length === 0 && <p className="loading">불러오는 중...</p>}
        {restaurants.map((r) => (
          <div key={r.id} className="restaurant-card" onClick={() => onSelect(r)}>
            <div className="name">{r.name}</div>
            <div className="card-grade-slot">
              {r.absolute_grade && (
                <>
                  <GradeBadges absolute={r.absolute_grade} relative={r.relative_grade} />
                  <span className="count">
                    다이어트 메뉴 {Math.round(r.good_menu_ratio * 100)}%
                  </span>
                </>
              )}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
