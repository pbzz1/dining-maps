import { useEffect, useMemo, useState } from "react";
import { fetchStats, fetchMenu, fetchDietGrade } from "../api";
import { NUTRIENT_LABELS, GRADE_RANK, SORT_OPTIONS, formatValue } from "../constants";
import { GradeBadges, GradeLegend } from "./GradeBadges";

function nutrientValue(item, name) {
  return item.nutrition.find((n) => n.nutrient_name === name)?.value ?? null;
}

function sortItems(items, key) {
  const sorted = [...items];
  // Ungraded / unreported items always sink to the bottom rather than sorting
  // as if they were zero.
  const rank = (g) => (g in GRADE_RANK ? GRADE_RANK[g] : 4);
  const asc = (n) => (a, b) => (nutrientValue(a, n) ?? Infinity) - (nutrientValue(b, n) ?? Infinity);
  const desc = (n) => (a, b) => (nutrientValue(b, n) ?? -Infinity) - (nutrientValue(a, n) ?? -Infinity);

  switch (key) {
    case "calorie_asc": return sorted.sort(asc("calorie"));
    case "calorie_desc": return sorted.sort(desc("calorie"));
    case "protein_desc": return sorted.sort(desc("protein"));
    case "grade_absolute": return sorted.sort((a, b) => rank(a.absolute_grade) - rank(b.absolute_grade));
    case "grade_relative": return sorted.sort((a, b) => rank(a.relative_grade) - rank(b.relative_grade));
    default: return sorted.sort((a, b) => a.name.localeCompare(b.name, "ko"));
  }
}

export default function MenuView({ restaurant, onBack }) {
  const [stats, setStats] = useState(null);
  const [grade, setGrade] = useState(null);
  const [menu, setMenu] = useState([]);
  const [sortKey, setSortKey] = useState("name");
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setSortKey("name");
    Promise.all([
      fetchStats(restaurant.id),
      fetchMenu(restaurant.id),
      fetchDietGrade(restaurant.id),
    ])
      .then(([s, m, g]) => {
        if (cancelled) return;
        setStats(s);
        setMenu(m);
        setGrade(g);
        setLoading(false);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e.message);
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [restaurant.id]);

  const sorted = useMemo(() => sortItems(menu, sortKey), [menu, sortKey]);

  return (
    <section>
      <button id="back-btn" onClick={onBack}>&larr; 매장 목록으로</button>
      <h2>{restaurant.name}</h2>
      <GradeLegend />

      {error && <p className="error">메뉴를 불러오지 못했습니다: {error}</p>}
      {loading && !error && <p className="loading">불러오는 중...</p>}

      {!loading && !error && (
        <>
          <div className="stats-bar">
            {grade?.absolute_grade ? (
              <span className="stat-chip grade-chip">
                <GradeBadges absolute={grade.absolute_grade} relative={grade.relative_grade} />
                {" "}절대/상대 등급 · 도움 메뉴 {Math.round(grade.good_menu_ratio * 100)}%
              </span>
            ) : (
              <span className="stat-chip">영양정보 부족 (등급 산출 불가 — 당류·포화지방·나트륨 미공개)</span>
            )}
            <span className="stat-chip">메뉴 {stats?.menu_item_count}개</span>
            {stats?.averages.map((a) => (
              <span key={a.nutrient_name} className="stat-chip">
                평균 {NUTRIENT_LABELS[a.nutrient_name] ?? a.nutrient_name}{" "}
                {formatValue(a.avg_value, a.unit)}
              </span>
            ))}
          </div>

          <div className="menu-toolbar">
            <span className="filter-label">정렬</span>
            <select value={sortKey} onChange={(e) => setSortKey(e.target.value)}>
              {SORT_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>

          <div className="menu-list">
            {sorted.map((item) => {
              const meta = [
                item.category,
                item.weight_g && `${item.weight_g}g`,
                item.price_krw && `${item.price_krw.toLocaleString()}원`,
              ].filter(Boolean);
              return (
                <div key={item.id} className="menu-item">
                  <div className="menu-item-head">
                    <span className="menu-item-name">
                      <GradeBadges absolute={item.absolute_grade} relative={item.relative_grade} />{" "}
                      {item.name}
                    </span>
                    <span className="menu-item-meta">{meta.join(" · ")}</span>
                  </div>
                  <div className="nutrition-row">
                    {item.nutrition.length === 0 ? (
                      <span className="menu-item-meta">영양정보 없음</span>
                    ) : (
                      item.nutrition.map((n) => (
                        <span key={n.nutrient_name} className="nutrient-badge">
                          {NUTRIENT_LABELS[n.nutrient_name] ?? n.nutrient_name}{" "}
                          <b>{formatValue(n.value, n.unit)}</b>
                        </span>
                      ))
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </section>
  );
}
