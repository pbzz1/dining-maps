import { Fragment, useEffect, useMemo, useState } from "react";
import { fetchNewMenus } from "../../api";
import { track } from "../../constants";

// 신메뉴 표. 원천은 크롤 diff(menu_change_log 'added') + 보도자료로 확인한
// released_at -- 자세한 건 app/new_menu/router.py. 정렬은 30행 이하라 클라이언트에서.
// 유튜브는 특정 영상 박제 대신 검색 링크 -- API 키 불필요, 죽은 링크 없음.

const num = (v, digits = 0) =>
  v == null ? "-" : v.toLocaleString("ko-KR", { maximumFractionDigits: digits });

const BASIS_LABEL = { per_100g: "100g당", per_total: "전체", per_serving: "" };

// 리뷰 영상은 사이즈·세트와 무관하니 검색어도 옵션 뗀 이름으로 건다.
const ytQuery = (m) => `${m.restaurant_name} ${m.base_name} 리뷰`;
// 임베드는 fetch_youtube_reviews.py가 캐시한 검색 1위 영상 ID 기준
// (검색 결과 자체의 임베드는 유튜브가 지원 종료). ID 없으면 검색 링크로 대체.
const youtubeEmbedUrl = (m) => `https://www.youtube.com/embed/${m.youtube_video_id}`;
const youtubeSearchUrl = (m) =>
  `https://www.youtube.com/results?search_query=${encodeURIComponent(ytQuery(m))}`;

const COL_COUNT = 11; // 임베드 행의 colSpan -- 헤더 열 수와 같아야 한다

// 브랜드는 같은 메뉴를 옵션마다 다른 행으로 준다 (단품/세트/라지세트, L·M·라지…).
// 옵션을 뗀 이름(base_name)은 서버가 계산해서 준다 -- app/new_menu/router.py의
// OPTION_SUFFIX_RE 한 곳에만 규칙을 두려고. 여기서는 그 키로 묶고, 남은 접미사를
// 옵션 이름으로 쓴다. 접미사가 없는 행이 곧 단품.
const groupKey = (m) => `${m.restaurant_id}|${m.base_name}`;
const optionLabel = (m) =>
  m.name.slice(m.base_name.length).replace(/[()（）]/g, "").trim() || "단품";

function groupByMenu(rows) {
  const map = new Map();
  for (const m of rows) {
    const key = groupKey(m);
    if (!map.has(key)) map.set(key, []);
    map.get(key).push(m);
  }
  // 이름이 짧은 것부터 = 접미사 없는 행이 맨 앞. 기본 선택이 세트가 아니라 단품이 된다.
  for (const options of map.values()) options.sort((a, b) => a.name.length - b.name.length);
  return [...map.entries()];
}

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
  const [picked, setPicked] = useState({}); // groupKey -> 선택한 옵션의 menu_item id
  // 유튜브 임베드가 펼쳐진 행 (한 번에 하나). 옵션을 바꿔도 같은 줄이므로 groupKey 기준.
  const [openKey, setOpenKey] = useState(null);

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

  // 정렬은 "지금 보고 있는 옵션"의 값 기준 -- 옵션을 바꾸면 그 줄이 따라 움직인다.
  const sorted = useMemo(() => {
    if (!rows) return null;
    const get = SORTS[sortKey].get;
    return groupByMenu(rows)
      .map(([key, options]) => ({
        key,
        options,
        sel: options.find((o) => o.id === picked[key]) ?? options[0],
      }))
      .sort((a, b) => {
        const va = get(a.sel), vb = get(b.sel);
        if (va == null) return 1;
        if (vb == null) return -1;
        return (va < vb ? -1 : va > vb ? 1 : 0) * dir;
      });
  }, [rows, sortKey, dir, picked]);

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
        출시일은 보도자료로 확인된 날짜, 없으면 크롤이 처음 본 날. 사이즈·세트처럼 옵션만
        다른 메뉴는 한 줄로 묶었고, 옵션을 누르면 그 옵션의 영양정보로 바뀐다. 열 제목을
        눌러 재정렬.
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
              {sorted.map(({ key, options, sel: m }) => {
                const cal = brandBadge(m.calorie_brand_pct, true, ["낮은 편", "중간", "높은 편"]);
                const pro = brandBadge(m.protein_brand_pct, false, ["적은 편", "중간", "많은 편"]);
                // 리뷰 영상은 메뉴 단위 -- 캐시된 영상 ID를 가진 옵션이 하나라도 있으면 그걸 쓴다.
                const yt = options.find((o) => o.youtube_video_id) ?? m;
                return (
                  <Fragment key={key}>
                  <tr>
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
                      {m.base_name}
                      {BASIS_LABEL[m.nutrition_basis] && (
                        <span className="mx-basis">{BASIS_LABEL[m.nutrition_basis]}</span>
                      )}
                      {options.length > 1 && (
                        <span className="nm-opts">
                          {options.map((o) => (
                            <button
                              key={o.id}
                              type="button"
                              className={`nm-opt ${o.id === m.id ? "on" : ""}`}
                              onClick={() => {
                                setPicked((p) => ({ ...p, [key]: o.id }));
                                track("new_menu_option", { menu: o.name });
                              }}
                            >
                              {optionLabel(o)}
                            </button>
                          ))}
                        </span>
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
                      <button
                        className={`nm-yt ${openKey === key ? "open" : ""}`}
                        onClick={() => {
                          setOpenKey(openKey === key ? null : key);
                          track("youtube_review_embed", { menu: m.base_name });
                        }}
                      >
                        <span className="nm-yt-ic" aria-hidden="true">▶</span>
                        유튜브
                        <span className="nm-yt-chev" aria-hidden="true">▼</span>
                      </button>
                    </td>
                  </tr>
                  {openKey === key && (
                    <tr className="nm-embed-row">
                      <td colSpan={COL_COUNT}>
                        <div className="nm-embed">
                          {yt.youtube_video_id ? (
                            /* 펼쳤을 때만 마운트 -- 닫으면 재생도 함께 멈춘다 */
                            <iframe
                              src={youtubeEmbedUrl(yt)}
                              title={`${m.base_name} 유튜브 리뷰`}
                              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                              allowFullScreen
                            />
                          ) : (
                            <p className="nm-embed-none">아직 연결된 리뷰 영상이 없습니다.</p>
                          )}
                          <a href={youtubeSearchUrl(m)} target="_blank" rel="noreferrer">
                            유튜브에서 전체 검색 결과 보기 ↗
                          </a>
                        </div>
                      </td>
                    </tr>
                  )}
                  </Fragment>
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
