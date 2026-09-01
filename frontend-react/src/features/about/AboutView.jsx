// 영양정보 산출 기준 설명 화면 (#about). 사이드바 NAV에는 없고, 헤더 기준일
// 링크와 GradeLegend의 "기준 자세히" 링크로만 들어온다 -- 한 번 읽고 끝나는
// 문서라 매일 쓰는 5개 탭과 나란히 둘 성질이 아니다.
// 원문은 docs/diet_score.md. 수치를 고칠 때 여기와 app/ 쪽이 같이 움직여야 한다.

const MEAL_ROWS = [
  ["단백질", "≥6.25g", "3.75~6.25g", "2.5~3.75g", "<2.5g", "식약처 고단백 표시기준(25%E) · 한국영양학회지(15%E) · 연세대 저열량식이 논문(≈10%E)"],
  ["당류", "—", "≤1.25g", "1.25~2.5g", ">2.5g", "WHO(2015) 이상적 목표 5%E / 권고 상한 10%E"],
  ["포화지방", "—", "≤0.6g", "0.6~0.8g", ">0.8g", "AHA/ACC 5~6%E · 2018 이상지질혈증 치료지침 7%E 미만"],
  ["나트륨", "—", "≤75mg", "75~100mg", ">100mg", "AHA 1일 1,500mg · WHO/미국 1일 2,000mg (2,000kcal 기준 환산)"],
];

const DRINK_ROWS = [
  ["열량", "≤40kcal", "≤150", "≤250", ">250", "40kcal = 식약처/FDA 저칼로리 표시기준 · 250kcal ≈ 한 끼 수준"],
  ["당류", "—", "≤5g", "≤25g", ">25g", "WHO 이상적 목표(5%E) 하루치 = 25g"],
  ["포화지방", "—", "≤1g", "≤4g", ">4g", "AHA 6%E(≈13g/일)의 약 1/3"],
];

function ScoreTable({ rows, unitHead }) {
  return (
    <div className="about-scroll">
      <table className="dash-table about-table">
        <thead>
          <tr>
            <th>{unitHead}</th><th>+2</th><th>+1</th><th>0</th><th>−1</th><th>근거</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([name, ...cells]) => (
            <tr key={name}>
              <td>{name}</td>
              {cells.map((c, i) => <td key={i}>{c}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function AboutView({ dataDate }) {
  return (
    <div className="dashboard">
      <section className="dash-card">
        <h2>영양정보는 어디서 왔나</h2>
        <p className="dash-sub">
          모든 수치는 <b>브랜드가 공식 홈페이지에 공개한 영양성분표</b>를 그대로 옮긴 것이다.
          자체 측정·추정값은 없다.
          {dataDate && <> 현재 표시되는 데이터의 기준일은 <b>{dataDate}</b>(마지막 품질 검사 통과 수집일).</>}
        </p>
        <p className="dash-footnote">
          영양성분 5종(열량·단백질·당류·포화지방·나트륨)을 모두 공개한 메뉴만 채점된다.
          점수가 없는 메뉴는 나쁜 게 아니라 <b>알 수 없다</b>는 뜻이다.
        </p>
      </section>

      <section className="dash-card">
        <h2>식사 기준 (meal)</h2>
        <p className="dash-sub">
          메뉴 <b>100kcal당</b> 값을 WHO·AHA·식약처·논문 기준선과 비교해 지표마다 점수를 매긴다.
        </p>
        <ScoreTable rows={MEAL_ROWS} unitHead="지표 (100kcal당)" />
        <p className="dash-footnote">
          합산 −4~+5 → <code>점수 = (합산 + 4) ÷ 9 × 100</code>.
          100kcal 미만 메뉴는 100kcal당 환산이 왜곡돼서 제외한다.
        </p>
      </section>

      <section className="dash-card">
        <h2>음료 기준 (drink)</h2>
        <p className="dash-sub">
          음료는 <b>1잔 절대량</b>으로 본다. 단백질·나트륨은 반영하지 않는다 —
          100kcal당으로 재면 "단백질 많은 라떼"가 아메리카노를 이기고, 5kcal 음료의 밀도는 의미가 없다.
        </p>
        <ScoreTable rows={DRINK_ROWS} unitHead="지표 (1잔)" />
        <p className="dash-footnote">
          합산 −3~+4 → <code>점수 = (합산 + 3) ÷ 7 × 100</code>. 100kcal 미만 제외 규칙은 적용하지 않는다.
        </p>
      </section>

      <section className="dash-card">
        <h2>등급 A·B·C·D 두 가지</h2>
        <p className="dash-sub">앱 곳곳에서 배지 두 개가 나란히 붙는 이유.</p>
        <ul className="about-list">
          <li>
            <b>절대 기준</b> (진한 배지) — 위 점수의 고정 컷: A 80점 이상 · B 60 · C 40 · 나머지 D.
            매장이 늘어도 움직이지 않는다.
          </li>
          <li>
            <b>상대 기준</b> (흐린 배지) — 현재 등록된 브랜드를 평균 점수로 줄 세워 상위 25%씩
            A/B/C/D로 4등분. "A = 지금 DB에서 상위 25%"라는 뜻이라 브랜드가 추가되면 바뀐다.
          </li>
        </ul>
        <p className="dash-footnote">상대 순위는 같은 기준(식사/음료) 안에서만 매긴다.</p>
      </section>

      <section className="dash-card">
        <h2>알아두면 좋은 한계</h2>
        <ul className="about-list">
          <li>
            <b>나트륨은 거의 모든 메뉴가 초과한다.</b> 버그가 아니라 국제 기준이 실제로 엄격하고
            외식 전반이 고나트륨이라는 뜻이다. 결과적으로 브랜드 순위는 단백질 점수가 가른다.
          </li>
          <li>
            <b>브랜드마다 표기 단위가 다르다.</b> BHC·교촌치킨은 100g 기준, 도미노피자는
            1회분(피자 150g) 기준이라 1인분 그대로인 브랜드와 직접 비교하면 안 된다.
          </li>
          <li>
            WHO·AHA 기준은 원래 <b>하루 식단 전체</b>에 대한 권고다. 낱개 메뉴에 적용하는 건
            영양성분표의 %DV 표기와 같은 방식이지만 의미가 완전히 같지는 않다.
          </li>
          <li>점수는 이산값 조합이라 소수점까지 정밀해 보여도 실제로는 성긴 척도다.</li>
        </ul>
      </section>

      <section className="dash-card">
        <h2>참고한 기준·문헌</h2>
        <ul className="about-list about-refs">
          <li>WHO. Guideline: Sugars intake for adults and children. 2015.</li>
          <li>U.S. Dietary Guidelines for Americans, 2015–2020.</li>
          <li>AHA/ACC 식이 가이드라인 (포화지방·나트륨 권장 섭취량).</li>
          <li>이상지질혈증 치료지침 제3장 생활요법, 2018.</li>
          <li>식품의약품안전처 식품등의 표시기준 — 영양성분 강조표시.</li>
          <li>장순옥. 단백질 섭취기준. 한국영양학회지 2011;44(4):338–343.</li>
          <li>이홍기 외. 비만 여성 단기 저열량 식사요법에서 체구성 성분의 변화. 가정의학회지 2004;25:21–27.</li>
        </ul>
      </section>
    </div>
  );
}
