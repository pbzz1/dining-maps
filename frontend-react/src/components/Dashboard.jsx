import { useEffect, useState } from "react";
import { fetchStatsBrands, fetchStatsQuality } from "../api";

// 대시보드. 원천은 /api/stats/* (mart 머티리얼라이즈드 뷰라 요청 비용이 거의 없다).
//
// 차트는 div 가로 막대로 그린다. 값 비교(크기)가 전부라 차트 라이브러리를 들일
// 이유가 없고, 등급 분포는 순서형(A→D)이라 단일 색상 램프가 맞다 -- 앱의 등급
// 배지색 4개는 인접 배치하면 색각이상(protan)에서 B/C가 ΔE 1.5로 사실상 같은
// 색이라 스택 바에 쓸 수 없다 (배지는 글자가 함께 있어 문제없음).

const NUTRIENT_TABS = [
  { key: "avg_calorie_kcal", label: "칼로리", unit: "kcal" },
  { key: "avg_sodium_mg", label: "나트륨", unit: "mg" },
  { key: "avg_sugar_g", label: "당류", unit: "g" },
  { key: "avg_protein_g", label: "단백질", unit: "g" },
];

// A→D 순서형 램프: --accent(#c1440e) 단일 색상, 밝음→어두움. D(최악)가 가장 짙다.
const GRADE_RAMP = { A: "#fbe9e0", B: "#eeb59a", C: "#d97b4d", D: "#c1440e" };
const GRADES = ["A", "B", "C", "D"];

function BarRow({ name, value, max, formatted }) {
  return (
    <div className="dash-bar-row">
      <span className="dash-bar-name">{name}</span>
      <div className="dash-bar-track">
        <div className="dash-bar-fill" style={{ width: `${(value / max) * 100}%` }} />
      </div>
      <span className="dash-bar-value">{formatted}</span>
    </div>
  );
}

function GradeStackRow({ b }) {
  const total = b.scored_count;
  if (!total) {
    return (
      <div className="dash-bar-row">
        <span className="dash-bar-name">{b.restaurant_name}</span>
        <span className="dash-stack-empty">채점 불가 (영양항목 부족)</span>
      </div>
    );
  }
  return (
    <div className="dash-bar-row">
      <span className="dash-bar-name">{b.restaurant_name}</span>
      <div className="dash-stack">
        {GRADES.map((g) => {
          const n = b[`grade_${g.toLowerCase()}`];
          if (!n) return null;
          return (
            <div
              key={g}
              className="dash-stack-seg"
              style={{ width: `${(n / total) * 100}%`, background: GRADE_RAMP[g] }}
              title={`${b.restaurant_name} ${g}등급 ${n}개 (${Math.round((n / total) * 100)}%)`}
            />
          );
        })}
      </div>
      <span className="dash-bar-value">{total}개</span>
    </div>
  );
}

export default function Dashboard() {
  const [brands, setBrands] = useState(null);
  const [quality, setQuality] = useState(null);
  const [nutrient, setNutrient] = useState(NUTRIENT_TABS[1]); // 나트륨이 이 서비스의 주제
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([fetchStatsBrands(), fetchStatsQuality()])
      .then(([b, q]) => {
        setBrands(b);
        setQuality(q);
      })
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <p className="dash-status">대시보드 로딩 실패: {error}</p>;
  if (!brands) return <p className="dash-status">불러오는 중…</p>;

  const totals = {
    brands: brands.length,
    menus: brands.reduce((s, b) => s + b.menu_count, 0),
    stores: brands.reduce((s, b) => s + b.store_count, 0),
    scored: brands.reduce((s, b) => s + b.scored_count, 0),
  };

  const scoreRows = brands.filter((b) => b.avg_score != null);
  const maxScore = Math.max(...scoreRows.map((b) => b.avg_score));

  const nutrientRows = brands
    .filter((b) => b[nutrient.key] != null)
    .sort((a, b) => b[nutrient.key] - a[nutrient.key]);
  const maxNutrient = Math.max(...nutrientRows.map((b) => b[nutrient.key]));

  return (
    <div className="dashboard">
      <div className="dash-kpis">
        {[
          ["브랜드", totals.brands],
          ["메뉴", totals.menus],
          ["매장 위치", totals.stores],
          ["채점된 메뉴", totals.scored],
        ].map(([label, v]) => (
          <div className="dash-kpi" key={label}>
            <span className="dash-kpi-label">{label}</span>
            <span className="dash-kpi-value">{v.toLocaleString("ko-KR")}</span>
          </div>
        ))}
      </div>

      <section className="dash-card">
        <h2>브랜드별 평균 다이어트 점수</h2>
        <p className="dash-sub">WHO/논문 기준 0–100점, 높을수록 건강한 메뉴 구성</p>
        {scoreRows.map((b) => (
          <BarRow
            key={b.restaurant_id}
            name={b.restaurant_name}
            value={b.avg_score}
            max={maxScore}
            formatted={b.avg_score.toFixed(1)}
          />
        ))}
      </section>

      <section className="dash-card">
        <h2>등급 분포</h2>
        <p className="dash-sub">
          브랜드별 메뉴 등급 비율 · 짙을수록 나쁜 등급
          <span className="dash-legend">
            {GRADES.map((g) => (
              <span key={g} className="dash-legend-item">
                <span className="dash-legend-swatch" style={{ background: GRADE_RAMP[g] }} />
                {g}
              </span>
            ))}
          </span>
        </p>
        {brands.map((b) => (
          <GradeStackRow key={b.restaurant_id} b={b} />
        ))}
        <details className="dash-table-details">
          <summary>표로 보기</summary>
          <table className="dash-table">
            <thead>
              <tr><th>브랜드</th><th>A</th><th>B</th><th>C</th><th>D</th><th>채점</th></tr>
            </thead>
            <tbody>
              {brands.map((b) => (
                <tr key={b.restaurant_id}>
                  <td>{b.restaurant_name}</td>
                  <td>{b.grade_a}</td><td>{b.grade_b}</td>
                  <td>{b.grade_c}</td><td>{b.grade_d}</td>
                  <td>{b.scored_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      </section>

      <section className="dash-card">
        <h2>영양소 평균</h2>
        <div className="dash-tabs">
          {NUTRIENT_TABS.map((t) => (
            <button
              key={t.key}
              className={`dash-tab ${t.key === nutrient.key ? "active" : ""}`}
              onClick={() => setNutrient(t)}
            >
              {t.label}
            </button>
          ))}
        </div>
        {nutrientRows.map((b) => (
          <BarRow
            key={b.restaurant_id}
            name={b.restaurant_name}
            value={b[nutrient.key]}
            max={maxNutrient}
            formatted={`${Math.round(b[nutrient.key]).toLocaleString("ko-KR")}${nutrient.unit}`}
          />
        ))}
        <p className="dash-footnote">
          메뉴 1개당 평균. 브랜드마다 판매 단위가 다른 점에 주의 --
          예: 도미노피자는 피자 한 판 기준이라 1인분 기준인 브랜드보다 값이 크게 나온다.
        </p>
      </section>

      <section className="dash-card">
        <h2>데이터 품질 (크롤 회차별)</h2>
        <p className="dash-sub">
          검증 게이트를 통과해야만 서빙 테이블에 반영된다. 실패한 회차는 데이터에 반영되지 않은 기록이다.
        </p>
        <table className="dash-table">
          <thead>
            <tr><th>회차</th><th>시각</th><th>실행</th><th>결과</th><th>검증</th><th>파서 이상 의심</th></tr>
          </thead>
          <tbody>
            {quality.map((q) => (
              <tr key={q.run_id}>
                <td>#{q.run_id}</td>
                <td>{q.started_at.slice(0, 16).replace("T", " ")}</td>
                <td>{q.source}</td>
                <td>
                  <span className={`dash-chip ${q.status === "passed" ? "ok" : "fail"}`}>
                    {q.status === "passed" ? "✓ 통과" : "✗ 차단"}
                  </span>
                </td>
                <td>
                  {q.checks_pass}/{q.checks_total}
                  {q.checks_fail > 0 && <strong className="dash-fail-n"> (fail {q.checks_fail})</strong>}
                </td>
                <td>{q.suspected_parser_bugs || "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {/* ponytail: 월별 영양 추이 차트는 아직 안 그린다. mart_nutrient_trend의
            5개 회차가 전부 같은 날이라 선 하나짜리 가짜 추이가 된다. 크롤 회차가
            두 달치 이상 쌓이면 여기에 회차별 라인 차트를 추가할 것. */}
        <p className="dash-footnote">
          월별 영양 변화 추이는 크롤 회차가 쌓이는 대로 이 자리에 표시됩니다.
        </p>
      </section>
    </div>
  );
}
