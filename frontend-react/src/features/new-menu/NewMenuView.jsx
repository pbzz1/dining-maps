import { useEffect, useMemo, useState } from "react";
import { fetchNewMenus } from "../../api";
import { track } from "../../constants";

// 신메뉴 표. 원천은 크롤 diff(menu_change_log 'added') + 보도자료로 확인한
// released_at -- 자세한 건 app/new_menu/router.py. 정렬은 30행 이하라 클라이언트에서.
// 유튜브는 특정 영상 박제 대신 검색 링크 -- API 키 불필요, 죽은 링크 없음.

const num = (v, digits = 0) =>
  v == null ? "-" : v.toLocaleString("ko-KR", { maximumFractionDigits: digits });

const BASIS_LABEL = { per_100g: "100g당", per_total: "전체", per_serving: "" };

const youtubeUrl = (m) =>
  `https://www.youtube.com/results?search_query=${encodeURIComponent(
    `${m.restaurant_name} ${m.name} 리뷰`
  )}`;

// 클릭 정렬 가능한 컬럼: key -> 값 추출. null은 항상 뒤로.
const SORTS = {
  date: { label: "출시일", get: (m) => m.event_date, defaultDir: -1 },
  brand: { label: "브랜드", get: (m) => m.restaurant_name, defaultDir: 1 },
  category: { label: "분류", get: (m) => m.category_group ?? "기타", defaultDir: 1 },
  calorie: { label: "칼로리", get: (m) => m.calorie, defaultDir: 1 },
  protein: { label: "단백질", get: (m) => m.protein, defaultDir: -1 },
  sugar: { label: "당류", get: (m) => m.sugar, defaultDir: 1 },
  sodium: { label: "나트륨", get: (m) => m.sodium, defaultDir: 1 },
  score: { label: "다이어트", get: (m) => m.diet_score, defaultDir: -1 },
};

// 같은 브랜드·같은 카테고리 내 백분위 -> "낮은 편/중간/높은 편" 배지.
// 칼로리는 낮을수록, 단백질은 높을수록 좋은 편(초록). 정확한 백분위는 툴팁에.
function brandBadge(pct, goodWhenLow, [lowLabel, midLabel, highLabel]) {
  if (pct == null) return null;
  const level = pct <= 33 ? "low" : pct >= 67 ? "high" : "mid";
  const good = goodWhenLow ? level === "low" : level === "high";
  const bad = goodWhenLow ? level === "high" : level === "low";
  return {
    cls: good ? "good" : bad ? "bad" : "mid",
    pos: { low: lowLabel, mid: midLabel, high: highLabel }[level],
    tip: `같은 브랜드·카테고리 내 백분위 ${Math.round(pct)} (0=최저, 100=최고)`,
  };
}

export default function NewMenuView() {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);
  const [sortKey, setSortKey] = useState("date");
  const [dir, setDir] = useState(-1); // 1 asc, -1 desc

  useEffect(() => {
    fetchNewMenus().then(setRows).catch((e) => setError(e.message));
  }, []);

  function clickSort(key) {
    if (key === sortKey) setDir(-dir);
    else {
      setSortKey(key);
      setDir(SORTS[key].defaultDir);
    }
    track("new_menu_sort", { key });
  }

  const sorted = useMemo(() => {
    if (!rows) return null;
    const get = SORTS[sortKey].get;
    return [...rows].sort((a, b) => {
      const va = get(a), vb = get(b);
      if (va == null) return 1;
      if (vb == null) return -1;
      return (va < vb ? -1 : va > vb ? 1 : 0) * dir;
    });
  }, [rows, sortKey, dir]);

  const th = (key) => (
    <th
      key={key}
      className={`nm-th ${sortKey === key ? "dash-td-hi" : ""}`}
      onClick={() => clickSort(key)}
    >
      {SORTS[key].label}
      {sortKey === key && <span className="nm-arrow">{dir === 1 ? "▲" : "▼"}</span>}
    </th>
  );

  return (
    <div className="nm-page">
      <h2 className="nm-title">신메뉴</h2>
      <p className="dash-sub">
        매일 크롤이 브랜드 공식 영양정보를 이전 회차와 비교해 새로 올라온 메뉴를 잡아낸다.
        출시일은 보도자료로 확인된 날짜, 없으면 크롤이 처음 본 날. 열 제목을 눌러 재정렬.
      </p>

      {error && <p className="dash-status">신메뉴 불러오기 실패: {error}</p>}
      {!error && sorted === null && <p className="dash-status">불러오는 중…</p>}
      {sorted?.length === 0 && (
        <p className="dash-status">
          최근 90일 안에 감지된 신메뉴가 없습니다. 브랜드가 새 메뉴를 공식 사이트에
          올리면 다음 크롤 때 자동으로 나타납니다.
        </p>
      )}

      {sorted?.length > 0 && (
        <div className="dash-table-scroll">
          <table className="dash-table nm-table">
            <thead>
              <tr>
                {th("date")}
                {th("brand")}
                <th>메뉴</th>
                {th("category")}
                {th("calorie")}
                {th("protein")}
                {th("sugar")}
                {th("sodium")}
                <th title="같은 브랜드·같은 카테고리 메뉴들 사이에서의 위치">브랜드 내</th>
                {th("score")}
                <th>리뷰</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((m) => {
                const cal = brandBadge(m.calorie_brand_pct, true, ["낮은 편", "중간", "높은 편"]);
                const pro = brandBadge(m.protein_brand_pct, false, ["적은 편", "중간", "많은 편"]);
                return (
                  <tr key={m.id}>
                    <td className="nm-cell-date">
                      {m.event_date}
                      {!m.released_at && <span className="nm-detected">발견</span>}
                    </td>
                    <td>{m.restaurant_name}</td>
                    <td className="nm-cell-name">
                      {/* no-referrer: 브랜드 CDN이 외부 referer를 막아도 이미지가 나오게 */}
                      {m.image_url && (
                        <img className="nm-thumb" src={m.image_url} alt="" loading="lazy" referrerPolicy="no-referrer" />
                      )}
                      {m.name}
                      {BASIS_LABEL[m.nutrition_basis] && (
                        <span className="mx-basis">{BASIS_LABEL[m.nutrition_basis]}</span>
                      )}
                    </td>
                    <td className="mx-cat">{m.category_group ?? "기타"}</td>
                    <td className={sortKey === "calorie" ? "dash-td-hi" : ""}>{num(m.calorie)}</td>
                    <td className={sortKey === "protein" ? "dash-td-hi" : ""}>{num(m.protein, 1)}g</td>
                    <td className={sortKey === "sugar" ? "dash-td-hi" : ""}>{num(m.sugar, 1)}g</td>
                    <td className={sortKey === "sodium" ? "dash-td-hi" : ""}>{num(m.sodium)}mg</td>
                    <td className="nm-cell-brandpos">
                      {cal && <span className={`nm-verdict ${cal.cls}`} title={cal.tip}>칼로리 {cal.pos}</span>}
                      {pro && <span className={`nm-verdict ${pro.cls}`} title={pro.tip}>단백질 {pro.pos}</span>}
                      {!cal && !pro && "-"}
                    </td>
                    <td className={sortKey === "score" ? "dash-td-hi" : ""}>
                      {m.diet_score == null
                        ? "-"
                        : `${m.diet_score.toFixed(0)}${m.absolute_grade ? ` (${m.absolute_grade})` : ""}`}
                    </td>
                    <td>
                      <a
                        className="nm-yt"
                        href={youtubeUrl(m)}
                        target="_blank"
                        rel="noreferrer"
                        onClick={() => track("youtube_review_search", { menu: m.name })}
                      >
                        ▶ 유튜브
                      </a>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <p className="dash-footnote">
        영양정보는 브랜드 공식 공개값 그대로다. '브랜드 내' 위치는 같은 브랜드의 같은
        카테고리 메뉴들 사이 백분위(칼로리는 낮을수록, 단백질은 높을수록 좋은 편).
        실제 맛·구성은 유튜브 리뷰로 확인하세요.
      </p>
    </div>
  );
}
