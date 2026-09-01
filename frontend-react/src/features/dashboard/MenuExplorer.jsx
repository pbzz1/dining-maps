import { useEffect, useState } from "react";
import { fetchMenus } from "../../api";

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

// 영양정보 표기 기준. 브랜드마다 달라서 칼로리·나트륨 같은 절대값을 나란히 세울 때
// 이걸 안 보여주면 "100g당 315kcal"과 "1인분 1,812kcal"이 같은 줄에서 비교된다.
const BASIS_LABEL = { per_100g: "100g당", per_total: "전체", per_serving: "" };

export default function MenuExplorer({ brands }) {
  const [sort, setSort] = useState(SORTS[0]);
  const [category, setCategory] = useState(null); // null = 전체
  const [restaurantId, setRestaurantId] = useState(null);
  const [query, setQuery] = useState(""); // 입력창 값 그대로
  const [q, setQ] = useState(""); // 디바운스된 실제 검색어
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);

  // 타이핑마다 요청하지 않게 300ms 디바운스
  useEffect(() => {
    const t = setTimeout(() => setQ(query.trim()), 300);
    return () => clearTimeout(t);
  }, [query]);

  useEffect(() => {
    setError(null);
    fetchMenus({
      sort: sort.key,
      limit: 20,
      ...(category ? { category } : {}),
      ...(restaurantId ? { restaurant_id: restaurantId } : {}),
      ...(q ? { q } : {}),
    })
      .then(setRows)
      .catch((e) => setError(e.message));
  }, [sort, category, restaurantId, q]);

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
            <strong>비율 정렬은 100kcal 이상만</strong> — '100kcal당 단백질'·'그램 대비
            단백질'은 100kcal 미만 메뉴를 제외한다. 브랜드가 단백질을 g 단위로 반올림해
            공개하기 때문에, 3kcal짜리 차의 '단백질 1g'을 비율로 바꾸면 반올림 오차가
            그대로 100kcal당 23g이 되어 1위를 차지한다. 중량을 공개한 메뉴만 줄 세울 수
            있는 '그램 대비'는 목록이 더 짧고, BHC·교촌처럼 100g 기준으로 공개하는
            브랜드는 계산이 성립하지 않아 빠진다.
            <br />
            <br />
            <strong>표기 기준</strong> — 메뉴 이름 옆의 <span className="mx-basis">100g당</span>
            {" "}·<span className="mx-basis">전체</span> 표시는 그 브랜드가 영양정보를 적은
            기준이다. 아무 표시가 없으면 1인분 기준. 칼로리·나트륨 같은 절대값을 브랜드끼리
            비교할 때는 이 표시를 함께 봐야 한다.
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
          <input
            type="search"
            className="mx-search"
            placeholder="메뉴 이름 검색"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="메뉴 이름 검색"
          />
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
          조건에 맞는 메뉴가 없습니다. {q ? `"${q}" 검색 결과가 없거나, ` : ""}이 정렬 기준에
          필요한 영양정보·중량을 공개하지 않았거나, 비율 정렬이라 100kcal 미만 메뉴가 전부
          제외됐을 수 있습니다 (음료 대부분이 여기 해당).
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
                  <td className="mx-name">
                    {m.name}
                    {BASIS_LABEL[m.nutrition_basis] && (
                      <span className="mx-basis">{BASIS_LABEL[m.nutrition_basis]}</span>
                    )}
                  </td>
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
