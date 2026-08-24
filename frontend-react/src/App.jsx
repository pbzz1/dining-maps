import { useEffect, useState } from "react";
import MapView from "./components/MapView";
import RestaurantList from "./components/RestaurantList";
import MenuView from "./components/MenuView";
import Dashboard from "./components/Dashboard";
import RecommendView from "./features/recommend/RecommendView";
import { fetchStatsQuality } from "./api";
import LogoMark from "./components/Logo";
import { IconDashboard, IconStar, IconPin, IconList } from "./components/NavIcons";
import "./App.css";

const NAV = [
  { key: "dashboard", label: "대시보드", Icon: IconDashboard },
  { key: "recommend", label: "맞춤 추천", Icon: IconStar },
  { key: "map", label: "지도", Icon: IconPin },
  { key: "list", label: "매장 목록", Icon: IconList },
];

const VIEWS = new Set(NAV.map((n) => n.key));
// URL 해시가 곧 현재 뷰 -- "#map" 같은 링크를 공유하면 그 탭으로 바로 열린다.
const viewFromHash = () => (VIEWS.has(location.hash.slice(1)) ? location.hash.slice(1) : "dashboard");

export default function App() {
  const [view, setViewRaw] = useState(viewFromHash); // map | list | menu | dashboard | recommend
  const [selected, setSelected] = useState(null);
  const [dataDate, setDataDate] = useState("");

  // GA4 custom event; gtag is absent under ad-blockers, hence the optional call.
  function setView(v) {
    window.gtag?.("event", "view_change", { view: v });
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
    window.gtag?.("event", "select_restaurant", { name: restaurant.name });
    setSelected(restaurant);
    setView("menu");
  }

  // "menu" is a drill-down from the list, so the list item stays highlighted.
  const activeNav = view === "menu" ? "list" : view;

  return (
    <div className="shell">
      <header className="topbar">
        {/* 로고 = 홈. 해시를 지우고 새로고침해서 첫 화면(대시보드)으로 완전히 초기화한다. */}
        <h1 className="brand">
          <a href="/">
            <LogoMark size={34} />
            <span className="wordmark">Dining Maps</span>
          </a>
        </h1>
        <span className="subtitle">
          내 주변 프랜차이즈, 목표에 맞는 메뉴 찾기
          {dataDate && ` · 브랜드 공식 영양정보 ${dataDate} 기준`}
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
        {view === "dashboard" && <Dashboard />}
        {view === "recommend" && <RecommendView />}
        {view === "list" && <RestaurantList onSelect={openMenu} />}
        {view === "menu" && selected && (
          <MenuView restaurant={selected} onBack={() => setView("list")} />
        )}
      </main>
    </div>
  );
}
