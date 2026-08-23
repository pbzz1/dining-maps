import { useState } from "react";
import MapView from "./components/MapView";
import RestaurantList from "./components/RestaurantList";
import MenuView from "./components/MenuView";
import Dashboard from "./components/Dashboard";
import "./App.css";

const NAV = [
  { key: "dashboard", label: "대시보드", icon: "▦" },
  { key: "map", label: "지도", icon: "◎" },
  { key: "list", label: "매장 목록", icon: "☰" },
];

export default function App() {
  const [view, setViewRaw] = useState("dashboard"); // map | list | menu | dashboard
  const [selected, setSelected] = useState(null);

  // GA4 custom event; gtag is absent under ad-blockers, hence the optional call.
  function setView(v) {
    window.gtag?.("event", "view_change", { view: v });
    setViewRaw(v);
  }

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
        <h1>Dining Maps</h1>
        <span className="subtitle">프랜차이즈 메뉴 영양정보 비교</span>
      </header>

      <aside className="sidebar">
        {NAV.map((n) => (
          <button
            key={n.key}
            className={`nav-btn ${activeNav === n.key ? "active" : ""}`}
            onClick={() => setView(n.key)}
          >
            <span className="nav-icon" aria-hidden="true">{n.icon}</span>
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
        {view === "list" && <RestaurantList onSelect={openMenu} />}
        {view === "menu" && selected && (
          <MenuView restaurant={selected} onBack={() => setView("list")} />
        )}
      </main>
    </div>
  );
}
