import { useState } from "react";

// 매장(브랜드) 탐색기. MenuExplorer 의 브랜드판 -- 컬럼 헤더를 눌러 기준을 바꾼다.
// 데이터는 Dashboard 가 이미 받아온 mart_brand_nutrition 그대로라 API 호출이 없고,
// 16개 행이라 클라이언트 정렬로 충분하다.

const COLUMNS = [
  { key: "store_count", label: "매장 수", fmt: (v) => v.toLocaleString("ko-KR") },
  { key: "menu_count", label: "메뉴 수", fmt: (v) => v.toLocaleString("ko-KR") },
  { key: "avg_score", label: "다이어트 점수", fmt: (v) => v.toFixed(1) },
  { key: "avg_calorie_kcal", label: "평균 칼로리", fmt: (v) => `${Math.round(v).toLocaleString("ko-KR")}kcal` },
  { key: "avg_sodium_mg", label: "평균 나트륨", fmt: (v) => `${Math.round(v).toLocaleString("ko-KR")}mg` },
  { key: "avg_sugar_g", label: "평균 당류", fmt: (v) => `${v.toFixed(1)}g` },
  { key: "avg_protein_g", label: "평균 단백질", fmt: (v) => `${v.toFixed(1)}g` },
];

export default function BrandExplorer({ brands }) {
  const [sortKey, setSortKey] = useState("avg_score");
  const [desc, setDesc] = useState(true);

  const toggle = (key) => {
    if (key === sortKey) setDesc(!desc);
    else {
      setSortKey(key);
      setDesc(true);
    }
  };

  // 정렬 기준 값이 없는 브랜드(영양 미공개 등)는 맨 아래로 보낸다.
  const rows = [...brands].sort((a, b) => {
    const av = a[sortKey], bv = b[sortKey];
    if (av == null) return 1;
    if (bv == null) return -1;
    return desc ? bv - av : av - bv;
  });

  return (
    <section className="dash-card">
      <h2>
        매장 탐색기
        <details className="dash-info">
          <summary aria-label="이 표 설명 보기">ⓘ</summary>
          <div className="dash-info-pop">
            <strong>무엇을 보여주나</strong> — 브랜드 16곳을 한 표에서 비교한다. 컬럼 제목을
            누르면 그 기준으로 정렬되고, 한 번 더 누르면 순서가 뒤집힌다.
            <br />
            <br />
            <strong>평균의 함정</strong> — 영양소 평균은 <em>메뉴 1개당</em> 값이라 판매 단위가
            큰 브랜드(피자 한 판, 치킨 한 마리)가 커 보인다. 브랜드끼리 공정하게 비교하려면
            판매 단위 영향이 없는 다이어트 점수를 보는 게 낫다.
            <br />
            <br />
            <strong>빈 칸</strong> — 영양정보를 공개하지 않았거나 매장 위치를 아직 수집하지
            않은 브랜드다.
          </div>
        </details>
      </h2>
      <p className="dash-sub">컬럼 제목을 눌러 정렬 기준을 바꾼다</p>
      <div className="dash-table-scroll">
        <table className="dash-table mx-table bx-table">
          <thead>
            <tr>
              <th>#</th>
              <th>브랜드</th>
              {COLUMNS.map((c) => (
                <th
                  key={c.key}
                  className={c.key === sortKey ? "dash-td-hi bx-sortable" : "bx-sortable"}
                  onClick={() => toggle(c.key)}
                  title="눌러서 이 기준으로 정렬"
                >
                  {c.label}
                  {c.key === sortKey ? (desc ? " ↓" : " ↑") : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((b, i) => (
              <tr key={b.restaurant_id}>
                <td className="mx-rank">{i + 1}</td>
                <td className="mx-name">{b.restaurant_name}</td>
                {COLUMNS.map((c) => (
                  <td key={c.key} className={c.key === sortKey ? "dash-td-hi" : undefined}>
                    {b[c.key] == null || (c.key === "store_count" && !b[c.key])
                      ? "-"
                      : c.fmt(Number(b[c.key]))}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
