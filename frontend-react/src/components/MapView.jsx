import { useCallback, useEffect, useRef, useState } from "react";
import { fetchStores } from "../api";
import { useKakaoMap } from "../useKakaoMap";
import {
  DEFAULT_CENTER, SEARCH_RADIUS_M, GRADE_COLOR, GRADE_CLASS, formatDistance,
} from "../constants";

export default function MapView({ onOpenMenu }) {
  const containerRef = useRef(null);
  const overlaysRef = useRef([]);
  const popupRef = useRef(null);
  const centerRef = useRef(DEFAULT_CENTER);

  const { map, places, ready, error: sdkError } = useKakaoMap(containerRef, DEFAULT_CENTER);

  const [stores, setStores] = useState([]);
  const [status, setStatus] = useState("");
  const [gradeType, setGradeType] = useState("relative");
  const [minGrade, setMinGrade] = useState("");
  const [keyword, setKeyword] = useState("");

  const clearOverlays = useCallback(() => {
    overlaysRef.current.forEach((o) => o.setMap(null));
    overlaysRef.current = [];
    if (popupRef.current) {
      popupRef.current.setMap(null);
      popupRef.current = null;
    }
  }, []);

  const showPopup = useCallback(
    (store) => {
      if (popupRef.current) popupRef.current.setMap(null);
      const ratio =
        store.good_menu_ratio != null ? `${Math.round(store.good_menu_ratio * 100)}%` : "-";

      const el = document.createElement("div");
      el.className = "store-popup";
      el.innerHTML = `
        <button class="store-popup-close" type="button">&times;</button>
        <div class="store-popup-title">${store.restaurant_name} ${store.branch_name}</div>
        <div class="store-popup-meta">절대 ${store.absolute_grade ?? "-"} · 상대 ${store.relative_grade ?? "-"} · 도움 메뉴 ${ratio}</div>
        <div class="store-popup-meta">${formatDistance(store.distance_m)}${store.address ? " · " + store.address : ""}</div>
        <button class="store-popup-menu-btn" type="button">이 브랜드 메뉴 보기</button>
      `;
      el.querySelector(".store-popup-close").addEventListener("click", () => {
        popupRef.current?.setMap(null);
        popupRef.current = null;
      });
      el.querySelector(".store-popup-menu-btn").addEventListener("click", () => {
        popupRef.current?.setMap(null);
        popupRef.current = null;
        onOpenMenu({ id: store.restaurant_id, name: store.restaurant_name });
      });

      const overlay = new window.kakao.maps.CustomOverlay({
        position: new window.kakao.maps.LatLng(store.lat, store.lng),
        content: el,
        yAnchor: 1.4,
        zIndex: 10,
      });
      overlay.setMap(map);
      popupRef.current = overlay;
    },
    [map, onOpenMenu]
  );

  const loadStores = useCallback(
    async (lat, lng) => {
      centerRef.current = { lat, lng };
      setStatus("매장 불러오는 중...");
      clearOverlays();
      try {
        const params = { lat, lng, radius_m: SEARCH_RADIUS_M, grade_type: gradeType };
        if (minGrade) params.min_grade = minGrade;
        const list = await fetchStores(params);
        setStores(list);
        setStatus(
          list.length === 0
            ? "조건에 맞는 매장이 없습니다. (필터를 완화해보세요)"
            : `주변 매장 ${list.length}곳 (거리순 정렬)`
        );
      } catch (e) {
        setStatus(`매장 정보를 불러오지 못했습니다: ${e.message}`);
      }
    },
    [gradeType, minGrade, clearOverlays]
  );

  // Initial load + reload whenever a filter changes (keeping the current center).
  useEffect(() => {
    if (!ready) return;
    loadStores(centerRef.current.lat, centerRef.current.lng);
  }, [ready, gradeType, minGrade]); // eslint-disable-line react-hooks/exhaustive-deps

  // Draw pins for whatever store list is current.
  useEffect(() => {
    if (!ready || !map) return;
    overlaysRef.current.forEach((o) => o.setMap(null));
    overlaysRef.current = [];

    stores.forEach((store) => {
      const displayGrade = gradeType === "absolute" ? store.absolute_grade : store.relative_grade;
      const el = document.createElement("div");
      el.className = "map-pin";
      el.style.background = GRADE_COLOR[displayGrade] ?? "#999";
      el.innerHTML = `<span>${displayGrade ?? "?"}</span>`;
      el.addEventListener("click", () => showPopup(store));

      const overlay = new window.kakao.maps.CustomOverlay({
        position: new window.kakao.maps.LatLng(store.lat, store.lng),
        content: el,
        yAnchor: 1,
      });
      overlay.setMap(map);
      overlaysRef.current.push(overlay);
    });
  }, [stores, ready, map, gradeType, showPopup]);

  function handleSearch() {
    const q = keyword.trim();
    if (!q || !places) return;
    setStatus("검색 중...");
    places.keywordSearch(q, (data, s) => {
      if (s !== window.kakao.maps.services.Status.OK || data.length === 0) {
        setStatus(`"${q}" 검색 결과가 없습니다.`);
        return;
      }
      const lat = parseFloat(data[0].y);
      const lng = parseFloat(data[0].x);
      map.setCenter(new window.kakao.maps.LatLng(lat, lng));
      loadStores(lat, lng);
    });
  }

  function handleLocate() {
    if (!navigator.geolocation) {
      setStatus("이 브라우저는 위치 정보를 지원하지 않습니다.");
      return;
    }
    setStatus("내 위치 확인 중...");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude, longitude } = pos.coords;
        map.setCenter(new window.kakao.maps.LatLng(latitude, longitude));
        loadStores(latitude, longitude);
      },
      () => setStatus("위치 권한이 거부되었습니다.")
    );
  }

  function focusStore(store) {
    map.setCenter(new window.kakao.maps.LatLng(store.lat, store.lng));
    map.setLevel(3);
    showPopup(store);
  }

  return (
    <section>
      <div className="map-controls">
        <input
          type="text"
          placeholder="지역/주소 검색 (예: 강남역)"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSearch()}
        />
        <button onClick={handleSearch}>검색</button>
        <button onClick={handleLocate}>내 위치</button>
      </div>

      <div className="filter-controls">
        <div className="filter-group">
          <span className="filter-label">등급 기준</span>
          {["relative", "absolute"].map((t) => (
            <button
              key={t}
              className={`grade-type-btn ${gradeType === t ? "active" : ""}`}
              onClick={() => setGradeType(t)}
            >
              {t === "relative" ? "상대 기준" : "절대 기준(WHO)"}
            </button>
          ))}
        </div>
        <div className="filter-group">
          <span className="filter-label">최소 등급</span>
          <select value={minGrade} onChange={(e) => setMinGrade(e.target.value)}>
            <option value="">전체</option>
            <option value="A">A 이상</option>
            <option value="B">B 이상</option>
            <option value="C">C 이상</option>
          </select>
        </div>
      </div>

      <p className="loading">{sdkError ?? status}</p>

      <div className="map-layout">
        <div id="map-container" ref={containerRef} />
        <div className="store-list">
          {stores.map((store) => {
            const g = gradeType === "absolute" ? store.absolute_grade : store.relative_grade;
            return (
              <div key={store.id} className="store-card" onClick={() => focusStore(store)}>
                <div className="store-card-head">
                  <span className={`grade-badge ${GRADE_CLASS[g] ?? ""}`}>{g ?? "?"}</span>
                  <span className="store-card-name">
                    {store.restaurant_name} {store.branch_name}
                  </span>
                  <span className="store-card-distance">{formatDistance(store.distance_m)}</span>
                </div>
                <div className="store-card-address">{store.address}</div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="map-legend">
        {["A", "B", "C", "D"].map((g) => (
          <span key={g}>
            <span className={`grade-badge ${GRADE_CLASS[g]}`}>{g}</span>등급
          </span>
        ))}
        <span>진한 배지=절대 기준(WHO) · 옅은 배지=상대 기준(현재 등록 매장 중 순위)</span>
      </div>
    </section>
  );
}
