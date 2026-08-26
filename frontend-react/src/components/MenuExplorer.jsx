import { useEffect, useState } from "react";
import { fetchMenus } from "../api";

// 대시보드의 메뉴 단위 분석. 위 차트들이 브랜드를 줄 세운다면 여기는 메뉴 2천여 건을
// 사용자가 고른 기준으로 줄 세운다.
//
// 정렬을 <select> 로 둔 이유: 기준이 11개라 칩으로 깔면 두 줄이 되고, 카테고리 칩과
// 섞여 무엇이 무엇인지 안 읽힌다. 시각적 비중은 카테고리(칩)에 준다.

const SORTS = [
  { key: "calorie_desc", label: "칼로리 높은순", col: "calorie_kcal" },
  { key: "calorie_asc", label: "칼로리 낮은순", col: "calorie_kcal" },
  { key: "sodium_desc", label: "나트륨 높은순", col: "sodium_mg" },
  { key: "sodium_asc", label: "나트륨 낮은순", col: "sodium_mg" },
  { key: "sugar_desc", label: "당류 높은순", col: "sugar_g" },
  { key: "sugar_asc", label: "당류 낮은순", col: "sugar_g" },
  { key: "protein_desc", label: "단백질 많은순", col: "protein_g" },
  { key: "protein_per_100g_desc", label: "그램 대비 단백질 높은순", col: "sort" },
  { key: "protein_per_100kcal_desc", label: "100kcal당 단백질 높은순", col: "sort" },
  { key: "score_desc", label: "다이어트 점수 높은순", col: "diet_score" },
  { key: "score_asc", label: "다이어트 점수 낮은순", col: "diet_score" },
];

// app/menu_category.py 의 GROUPS 와 같은 순서.
const CATEGORIES = ["버거", "치킨", "피자", "샐러드·샌드위치", "음료", "디저트", "사이드", "기타"];

const num = (v, digits = 0) =>
  v == null ? "-" : v.toLocaleString("ko-KR", { maximumFractionDigits: digits });

export default function MenuExplorer({ brands }) {
  const [sort, setSort] = useState(SORTS[0]);
  const [category, setCategory] = useState(null); // null = 전체
  const [restaurantId, setRestaurantId] = useState(null);
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    setError(null);
    fetchMenus({
      sort: sort.key,
      limit: 20,
      ...(category ? { category } : {}),
      ...(restaurantId ? { restaurant_id: restaurantId } : {}),
    })
      .then(setRows)
      .catch((e) => setError(e.message));
  }, [sort, category, restaurantId]);

  // 정렬 기준 컬럼만 강조한다 -- 어떤 기준으로 줄 세웠는지가 표에서 바로 보이게.
  const hi = (col) => (sort.col === col ? "dash-td-hi" : undefined);

  return (
    <section className="dash-card">
      <h2>
        메뉴 탐색기
        <details className="dash-info">
          <summary aria-label="이 표 설명 보기">ⓘ</summary>
          <div className="dash-info-pop">
            <strong>무엇을 보여주나</strong> — 위 차트들이 브랜드를 비교한다면, 여기는 메뉴
            하나하나를 비교한다. 카테고리·브랜드로 좁히고 원하는 기준으로 줄 세운 상위 20개.
            <br />
            <br />
            <strong>카테고리는 어디서 오나</strong> — 브랜드가 준 원본 분류는 제각각이라(버거킹은
            분류 칸에 메뉴 이름이 그대로 들어있고 맥도날드는 아예 비어 있다) 메뉴명과 원본
            분류를 함께 보고 8개 그룹으로 다시 묶었다. 어디에도 안 맞으면 '기타'다.
            <br />
            <br />
            <strong>그램 대비 단백질</strong> — 중량을 공개한 메뉴만 줄 세울 수 있어 목록이
            짧아진다. 중량을 안 밝힌 브랜드까지 보려면 '100kcal당 단백질'을 쓰면 된다.
          </div>
        </details>
      </h2>
      <p className="dash-sub">카테고리·브랜드로 거르고 기준을 골라 상위 20개를 본다</p>

      <div className="mx-filters">
        <div className="dash-tabs">
          <button
            className={`dash-tab ${category === null ? "active" : ""}`}
            onClick={() => setCategory(null)}
          >
            전체
          </button>
          {CATEGORIES.map((c) => (
            <button
              key={c}
              className={`dash-tab ${category === c ? "active" : ""}`}
              onClick={() => setCategory(c)}
            >
              {c}
            </button>
          ))}
        </div>

        <div className="mx-selects">
          <label>
            <span>정렬</span>
            <select
              value={sort.key}
              onChange={(e) => setSort(SORTS.find((s) => s.key === e.target.value))}
            >
              {SORTS.map((s) => (
                <option key={s.key} value={s.key}>{s.label}</option>
              ))}
            </select>
          </label>
          <label>
            <span>브랜드</span>
            <select
              value={restaurantId ?? ""}
              onChange={(e) => setRestaurantId(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">전체</option>
              {brands.map((b) => (
                <option key={b.restaurant_id} value={b.restaurant_id}>{b.restaurant_name}</option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {error && <p className="dash-status">메뉴 불러오기 실패: {error}</p>}
      {!error && rows === null && <p className="dash-status">불러오는 중…</p>}
      {rows?.length === 0 && (
        <p className="dash-status">
          조건에 맞는 메뉴가 없습니다. 이 정렬 기준에 필요한 영양정보나 중량을 공개하지 않은
          브랜드일 수 있습니다.
        </p>
      )}

      {rows?.length > 0 && (
        <div className="dash-table-scroll">
          <table className="dash-table mx-table">
            <thead>
              <tr>
                <th>#</th>
                <th>메뉴</th>
                <th>브랜드</th>
                <th>분류</th>
                {sort.col === "sort" && <th className="dash-td-hi">{sort.label.replace(" 높은순", "")}</th>}
                <th className={hi("calorie_kcal")}>칼로리</th>
                <th className={hi("protein_g")}>단백질</th>
                <th className={hi("sugar_g")}>당류</th>
                <th className={hi("sodium_mg")}>나트륨</th>
                <th className={hi("diet_score")}>다이어트</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((m, i) => (
                <tr key={m.id}>
                  <td className="mx-rank">{i + 1}</td>
                  <td className="mx-name">{m.name}</td>
                  <td>{m.restaurant_name}</td>
                  <td className="mx-cat">{m.category_group}</td>
                  {sort.col === "sort" && (
                    <td className="dash-td-hi">{num(m.sort_value, 1)}{m.sort_unit}</td>
                  )}
                  <td className={hi("calorie_kcal")}>{num(m.calorie_kcal)}</td>
                  <td className={hi("protein_g")}>{num(m.protein_g, 1)}g</td>
                  <td className={hi("sugar_g")}>{num(m.sugar_g, 1)}g</td>
                  <td className={hi("sodium_mg")}>{num(m.sodium_mg)}mg</td>
                  <td className={hi("diet_score")}>
                    {m.diet_score == null ? "-" : `${m.diet_score.toFixed(0)}${m.absolute_grade ? ` (${m.absolute_grade})` : ""}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="dash-footnote">
        영양정보는 브랜드가 공개한 값 그대로다. 표기 기준이 브랜드마다 달라(BHC·교촌치킨은
        100g, 도미노피자는 1회분 150g) 칼로리·나트륨 절대값을 브랜드끼리 비교할 때는 주의해야 한다.
      </p>
    </section>
  );
}
