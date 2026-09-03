import { useEffect, useState } from "react";
import MapView from "./features/map/MapView";
import RestaurantList from "./features/restaurants/RestaurantList";
import MenuView from "./features/restaurants/MenuView";
import Dashboard from "./features/dashboard/Dashboard";
import RecommendView from "./features/recommend/RecommendView";
import NewMenuView from "./features/new-menu/NewMenuView";
import AboutView from "./features/about/AboutView";
import { fetchStatsQuality } from "./api";
import { track } from "./constants";
import LogoMark from "./components/Logo";
import { IconDashboard, IconStar, IconPin, IconList, IconSparkle } from "./components/NavIcons";
import "./App.css";

const NAV = [
  { key: "map", label: "지도", Icon: IconPin },
  { key: "recommend", label: "맞춤 추천", Icon: IconStar },
  { key: "new", label: "신메뉴", Icon: IconSparkle },
  { key: "dashboard", label: "대시보드", Icon: IconDashboard },
  { key: "list", label: "매장 목록", Icon: IconList },
];

// about은 NAV에 없다 -- 사이드바엔 안 뜨지만 #about 링크로는 열린다.
const VIEWS = new Set([...NAV.map((n) => n.key), "about"]);
// URL 해시가 곧 현재 뷰 -- "#list" 같은 링크를 공유하면 그 탭으로 바로 열린다.
// 기본 화면은 지도: Dining Maps니까.
const viewFromHash = () => (VIEWS.has(location.hash.slice(1)) ? location.hash.slice(1) : "map");

function useScrollDepthTracking(view) {
  useEffect(() => {
    const fired = new Set();
    function onScroll() {
      const doc = document.documentElement;
      const pct = Math.round((window.scrollY / Math.max(doc.scrollHeight - window.innerHeight, 1)) * 100);
      for (const t of [25, 50, 75]) {
        if (pct >= t && !fired.has(t)) {
          fired.add(t);
          track("scroll_depth", { view, percent: t });
        }
      }
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [view]);
}

// 한 번 방문한 뷰는 기억해 뒀다가 계속 마운트해 둔다. App은 화면에 하나뿐이라
// 모듈 스코프 Set이면 충분하고, 상태로 들 때처럼 렌더가 한 번 더 돌지도 않는다.
const seen = new Set();

// 방문한 적 있는 뷰만 렌더하고, 현재 뷰가 아니면 숨기기만 한다 (언마운트 X).
function Pane({ name, view, seen, children }) {
  if (!seen.has(name)) return null;
  return (
    <div className="view-wrap" style={{ display: view === name ? "flex" : "none" }}>
      {children}
    </div>
  );
}

export default function App() {
  const [view, setViewRaw] = useState(viewFromHash); // map | list | menu | dashboard | recommend
  const [selected, setSelected] = useState(null);
  const [dataDate, setDataDate] = useState("");
  // 한 번 방문한 뷰는 언마운트하지 않는다 -- 돌아왔을 때 이미 떠 있게. MapView가 쓰던
  // display:none 방식을 나머지 뷰로 넓힌 것. 처음부터 전부 마운트하면 첫 진입에 API가
  // 다섯 개 동시에 나가니, 마운트는 그 뷰를 실제로 열어본 시점에.
  seen.add(view);

  // GA4 custom event; gtag is absent under ad-blockers, hence the optional call.
  function setView(v) {
    track("view_change", { view: v });
    setViewRaw(v);
    if (VIEWS.has(v) && location.hash !== `#${v}`) history.pushState(null, "", `#${v}`);
  }

  useEffect(() => {
    const onHash = () => setViewRaw(viewFromHash()); // 뒤로가기
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  // 마지막으로 품질 게이트를 통과한 크롤 날짜 = 데이터 기준일.
  useEffect(() => {
    fetchStatsQuality()
      .then((rows) => {
        const ok = rows.filter((r) => r.status === "passed").at(-1);
        if (ok) setDataDate(ok.started_at.slice(0, 10));
      })
      .catch(() => {});
  }, []);

  function openMenu(restaurant) {
    track("select_restaurant", { name: restaurant.name });
    setSelected(restaurant);
    setView("menu");
  }

  // "menu" is a drill-down from the list, so the list item stays highlighted.
  const activeNav = view === "menu" ? "list" : view;
  useScrollDepthTracking(activeNav);

  // 모바일에서 내비는 가로 스크롤 줄이라 현재 탭이 화면 밖일 수 있다 -- 잘려 있으면 끌어온다.
  useEffect(() => {
    document.querySelector(".nav-btn.active")?.scrollIntoView({ inline: "nearest", block: "nearest" });
  }, [activeNav]);

  return (
    <div className="shell">
      <header className="topbar">
        {/* 로고 = 홈. 해시를 지우고 새로고침해서 첫 화면(지도)으로 완전히 초기화한다. */}
        <h1 className="brand">
          <a href="/">
            <LogoMark size={34} />
            <span className="wordmark">Dining Maps</span>
          </a>
        </h1>
        <span className="subtitle">
          내 주변 프랜차이즈, 목표에 맞는 메뉴 찾기
          {" · "}
          {/* 기준일을 아직 못 받아왔어도 링크는 남긴다 -- 데스크톱의 유일한 #about 진입점. */}
          <a href="#about" onClick={() => track("view_change", { view: "about" })}>
            브랜드 공식 영양정보{dataDate && ` ${dataDate}`} 기준
          </a>
        </span>
      </header>

      <aside className="sidebar">
        {NAV.map((n) => (
          <button
            key={n.key}
            className={`nav-btn ${activeNav === n.key ? "active" : ""}`}
            onClick={() => setView(n.key)}
          >
            <span className="nav-icon"><n.Icon /></span>
            {n.label}
          </button>
        ))}
      </aside>

      <main id="app" className={view === "map" ? "main-map" : "main-page"}>
        {/* MapView stays mounted (just hidden) so the Kakao map instance and its
            markers survive tab switches -- rebuilding it each time is slow and
            would lose the current center. */}
        <div className="map-wrap" style={{ display: view === "map" ? "flex" : "none" }}>
          <MapView onOpenMenu={openMenu} visible={view === "map"} />
        </div>
        <Pane name="dashboard" view={view} seen={seen}><Dashboard /></Pane>
        <Pane name="recommend" view={view} seen={seen}><RecommendView /></Pane>
        <Pane name="new" view={view} seen={seen}><NewMenuView /></Pane>
        <Pane name="about" view={view} seen={seen}><AboutView dataDate={dataDate} /></Pane>
        <Pane name="list" view={view} seen={seen}><RestaurantList onSelect={openMenu} /></Pane>
        {/* 드릴다운은 매장마다 내용이 달라 keep-alive 대상이 아니다 -- api.js 캐시가 커버. */}
        {view === "menu" && selected && (
          <div className="view-wrap" style={{ display: "flex" }}>
            <MenuView restaurant={selected} onBack={() => setView("list")} />
          </div>
        )}
      </main>
    </div>
  );
}
