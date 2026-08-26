import { useEffect, useState } from "react";
import { track } from "../constants";
import { fetchStatsBrands, fetchStatsQuality } from "../api";
import MenuExplorer from "./MenuExplorer";

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

// 차트 제목 옆 ⓘ. 각 차트가 무엇을 보여주는지 클릭하면 뜨는 설명.
// <details>라서 열림 상태를 들고 있을 필요가 없다.
function InfoPop({ children }) {
  return (
    <details className="dash-info">
      <summary aria-label="이 차트 설명 보기">ⓘ</summary>
      <div className="dash-info-pop">{children}</div>
    </details>
  );
}

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
        <h2>
          브랜드별 평균 다이어트 점수
          <InfoPop>
            <strong>무엇을 보여주나</strong> — 브랜드마다 파는 메뉴들이 평균적으로 얼마나
            건강한 구성인지. 막대가 길수록 좋다.
            <br />
            <br />
            <strong>어떻게 계산하나</strong> — 메뉴 1개당 100kcal 기준으로 단백질·당류·포화지방·
            나트륨 4개 지표를 WHO/AHA/식약처 기준선과 비교해 각각 -1~+2점을 매기고(최저 -4,
            최고 5), 합산 점수를 0~100점으로 환산한다. 브랜드 점수는 그 브랜드 메뉴들의 평균.
            <br />
            <br />
            <strong>주의</strong> — 영양성분 5종을 모두 공개한 메뉴만 채점된다. 100kcal 미만
            메뉴는 100kcal당 환산이 무의미해 제외. 음료는 1잔 기준 열량·당류·포화지방만으로 따로 채점(단백질·나트륨 미반영).
          </InfoPop>
        </h2>
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
        <h2>
          등급 분포
          <InfoPop>
            <strong>무엇을 보여주나</strong> — 위 차트가 브랜드의 평균 한 값이라면, 여기는 그
            평균 뒤에 숨은 분포다. 막대 하나가 그 브랜드 메뉴 100%이고, 색 구간의 폭이 각
            등급의 비율. 평균이 같아도 A와 D로 갈리는 브랜드와 전부 C인 브랜드는 다르다.
            <br />
            <br />
            <strong>등급 기준</strong> — 다이어트 점수의 절대 기준: A는 80점 이상, B는 60점
            이상, C는 40점 이상, 나머지는 D. 카탈로그가 바뀌어도 움직이지 않는 고정 컷.
            <br />
            <br />
            <strong>채점 불가</strong> — 영양성분을 충분히 공개하지 않은 브랜드는 막대가 없다.
            점수가 나쁘다는 뜻이 아니라 알 수 없다는 뜻.
          </InfoPop>
        </h2>
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
        <h2>
          영양소 평균
          <InfoPop>
            <strong>무엇을 보여주나</strong> — 점수로 합치기 전의 원본 수치. 탭을 눌러 지표를
            바꾸면 브랜드가 그 지표 기준으로 다시 정렬된다(높은 순).
            <br />
            <br />
            <strong>점수 차트와 다른 점</strong> — 다이어트 점수는 100kcal당으로 환산해 비교
            가능하게 만든 값이지만, 여기는 <em>메뉴 1개당 실제 평균</em>이다. 그래서 막대가
            길다고 나쁜 메뉴라는 뜻은 아니다 — 양이 많은 메뉴일 수도 있다.
            <br />
            <br />
            <strong>주의</strong> — 브랜드마다 표기 기준이 다르다. BHC·교촌치킨은 100g 기준,
            도미노피자는 1회분(피자 150g) 기준이라 1인분 그대로인 브랜드와 직접 비교하면 안 된다.
          </InfoPop>
        </h2>
        <div className="dash-tabs">
          {NUTRIENT_TABS.map((t) => (
            <button
              key={t.key}
              className={`dash-tab ${t.key === nutrient.key ? "active" : ""}`}
              onClick={() => { track("dashboard_nutrient_tab", { nutrient: t.key }); setNutrient(t); }}
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
          메뉴 1개당 평균. 브랜드마다 표기 기준이 다른 점에 주의 --
          예: BHC·교촌치킨은 100g 기준, 도미노피자는 1회분(피자 150g) 기준이다.
        </p>
      </section>

      <MenuExplorer brands={brands} />

      <section className="dash-card">
        <h2>
          데이터 품질 (크롤 회차별)
          <InfoPop>
            <strong>무엇을 보여주나</strong> — 위 차트들이 <em>무엇을</em> 보여주는가라면, 이
            표는 그 숫자를 <em>믿어도 되는가</em>에 대한 기록이다. 크롤을 돌릴 때마다 검증
            체크를 걸고, 통과한 회차만 화면에 쓰는 서빙 테이블에 반영한다.
            <br />
            <br />
            <strong>열 읽는 법</strong> — <em>실행</em>은 수동(manual)인지 스케줄러(airflow)인지.{" "}
            <em>검증</em>은 통과/전체 체크 수. <em>파서 이상 의심</em>은 값이 튀어 크롤러
            버그로 의심되는 항목 수다.
            <br />
            <br />
            <strong>차단된 회차</strong> — ✗ 표시는 실패한 크롤이 <em>막힌</em> 기록이지 나쁜
            데이터가 들어간 기록이 아니다. 게이트가 일한 흔적.
          </InfoPop>
        </h2>
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
