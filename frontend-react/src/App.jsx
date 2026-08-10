import { useState } from "react";
import MapView from "./components/MapView";
import RestaurantList from "./components/RestaurantList";
import MenuView from "./components/MenuView";
import "./App.css";

export default function App() {
  const [view, setView] = useState("map"); // map | list | menu
  const [selected, setSelected] = useState(null);

  function openMenu(restaurant) {
    setSelected(restaurant);
    setView("menu");
  }

  return (
    <>
      <header className="topbar">
        <h1>Dining Maps</h1>
        <p className="subtitle">프랜차이즈 메뉴 영양정보 비교</p>
        <nav className="top-nav">
          <button
            className={`nav-btn ${view !== "map" ? "active" : ""}`}
            onClick={() => setView("list")}
          >
            매장 목록
          </button>
          <button
            className={`nav-btn ${view === "map" ? "active" : ""}`}
            onClick={() => setView("map")}
          >
            지도
          </button>
        </nav>
      </header>

      <main id="app">
        {/* MapView stays mounted (just hidden) so the Kakao map instance and its
            markers survive tab switches -- rebuilding it each time is slow and
            would lose the current center. */}
        <div style={{ display: view === "map" ? "block" : "none" }}>
          <MapView onOpenMenu={openMenu} />
        </div>
        {view === "list" && <RestaurantList onSelect={openMenu} />}
        {view === "menu" && selected && (
          <MenuView restaurant={selected} onBack={() => setView("list")} />
        )}
      </main>
    </>
  );
}
