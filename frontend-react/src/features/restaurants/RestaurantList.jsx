import { useEffect, useState } from "react";
import { track } from "../../constants";
import { fetchRestaurants } from "../../api";
import { GradeLegend } from "../../components/GradeBadges";
import BrandAvatar from "../../components/BrandAvatar";
import Skel, { SkelBlock } from "../../components/Skeleton";
import { BRAND_SLUGS, ALL_GRADES, GRADE_CLASS, GRADE_COLOR, TIER_CAPTION, gradeTint, gradeBorder } from "../../constants";

export default function RestaurantList({ onSelect }) {
  const [restaurants, setRestaurants] = useState([]);
  const [error, setError] = useState(null);
  // 빈 배열은 "아직 안 왔다"와 "0건"을 구분 못 한다 -- 로딩은 따로 들고 간다.
  const [loading, setLoading] = useState(true);
  // Showing both grades at once on every card reads as noise -- default to
  // the one people actually compare stores by, let them switch to the fixed
  // WHO/논문 one when they want that instead. Tiers below group by this same
  // grade, so switching the toggle re-sorts stores into different rows too.
  const [gradeMode, setGradeMode] = useState("relative");

  useEffect(() => {
    let cancelled = false;
    // Grades come inlined on /api/restaurants -- one request for the whole page.
    fetchRestaurants()
      .then((list) => {
        if (cancelled) return;
        setRestaurants(list);
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
          onClick={() => { track("list_grade_mode", { mode: "relative" }); setGradeMode("relative"); }}
        >
          상대 기준
        </button>
        <button
          type="button"
          className={gradeMode === "absolute" ? "active" : ""}
          onClick={() => { track("list_grade_mode", { mode: "absolute" }); setGradeMode("absolute"); }}
        >
          절대 기준
        </button>
      </div>
      <GradeLegend mode={gradeMode} />
      {loading && (
        <SkelBlock label="매장 목록 불러오는 중">
          <div className="card-grid">
            {[0, 1, 2, 3, 4, 5].map((i) => <Skel key={i} h={128} r={12} />)}
          </div>
        </SkelBlock>
      )}
      {!loading && restaurants.length === 0 && <p className="loading">표시할 매장이 없습니다.</p>}
      {tiers.map(({ grade, items }) => (
        <div key={grade} className="tier-row">
          <div className={`tier-label ${GRADE_CLASS[grade]}`}>
            <span className="tier-letter">{grade}</span>
            <span className="tier-caption">{TIER_CAPTION[gradeMode][grade]}</span>
          </div>
          <div className="card-grid">
            {items.map((r) => (
              <div
                key={r.id}
                className="restaurant-card"
                style={{ background: gradeTint(grade), borderColor: gradeBorder(grade) }}
                onClick={() => onSelect(r)}
              >
                <BrandAvatar name={r.name} slug={BRAND_SLUGS[r.name]} ring={GRADE_COLOR[grade]} />
                <div className="name">{r.name}</div>
              </div>
            ))}
          </div>
        </div>
      ))}
      {ungraded.length > 0 && (
        <div className="tier-row">
          <div className="tier-label tier-label-none">
            <span className="tier-letter">-</span>
            <span className="tier-caption">정보 부족</span>
          </div>
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
