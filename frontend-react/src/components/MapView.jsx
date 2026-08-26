import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchStores } from "../api";
import { useKakaoMap } from "../useKakaoMap";
import {
  DEFAULT_CENTER, SEARCH_RADIUS_M, GRADE_COLOR, GRADE_CLASS, GRADE_RANK, ALL_GRADES, formatDistance,
} from "../constants";

// 주변 매장 전부가 아니라 "다이어트로 그나마 추천할 만한" 상위 N곳만 보여준다.
const RECOMMEND_LIMIT = 15;

export default function MapView({ onOpenMenu, visible = true }) {
  const containerRef = useRef(null);
  const overlaysRef = useRef([]);
  const popupRef = useRef(null);
  const centerRef = useRef(DEFAULT_CENTER);

  const { map, places, ready, error: sdkError } = useKakaoMap(containerRef, DEFAULT_CENTER);

  const [stores, setStores] = useState([]);
  const [status, setStatus] = useState("");
  const [gradeType, setGradeType] = useState("relative");
  const [activeGrades, setActiveGrades] = useState(() => new Set(ALL_GRADES));
  const [keyword, setKeyword] = useState("");

  function toggleGrade(g) {
    setActiveGrades((prev) => {
      const next = new Set(prev);
      next.has(g) ? next.delete(g) : next.add(g);
      return next;
    });
  }

  // A/B/C/D 온오프는 클라이언트에서 필터링한다 -- /api/stores의 min_grade는
  // "이 등급 이상"만 지원해서 서버에서 임의 조합(예: A,C만 켜기)을 걸 수 없다.
  // 그 다음 브랜드당 최근접 매장 1곳으로 추리고, 등급 좋은순 → 가까운순으로
  // 상위 15곳만 남긴다 -- 같은 브랜드 지점 15개를 "추천"이라고 줄세우지 않기 위해.
  const visibleStores = useMemo(() => {
    const gradeOf = (s) => (gradeType === "absolute" ? s.absolute_grade : s.relative_grade);
    const nearestPerBrand = new Map();
    for (const s of stores) {
      const g = gradeOf(s);
      if (g != null && !activeGrades.has(g)) continue;
      const prev = nearestPerBrand.get(s.restaurant_id);
      if (!prev || (s.distance_m ?? Infinity) < (prev.distance_m ?? Infinity)) {
        nearestPerBrand.set(s.restaurant_id, s);
      }
    }
    return [...nearestPerBrand.values()]
      .sort(
        (a, b) =>
          (GRADE_RANK[gradeOf(a)] ?? 9) - (GRADE_RANK[gradeOf(b)] ?? 9) ||
          (a.distance_m ?? 0) - (b.distance_m ?? 0)
      )
      .slice(0, RECOMMEND_LIMIT);
  }, [stores, gradeType, activeGrades]);

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
        const list = await fetchStores(params);
        setStores(list);
        setStatus(
          list.length === 0
            ? "주변에 매장이 없습니다."
            : `주변 매장 ${list.length}곳 중 다이어트 추천 상위 ${Math.min(RECOMMEND_LIMIT, new Set(list.map((s) => s.restaurant_id)).size)}곳`
        );
      } catch (e) {
        setStatus(`매장 정보를 불러오지 못했습니다: ${e.message}`);
      }
    },
    [gradeType, clearOverlays]
  );

  // The map is mounted inside a display:none wrapper when another tab is the
  // first screen, so Kakao sizes it to 0x0 and only paints a few tiles. Tell it
  // to re-measure each time the tab becomes visible.
  useEffect(() => {
    if (!visible || !map) return;
    map.relayout();
    map.setCenter(new window.kakao.maps.LatLng(centerRef.current.lat, centerRef.current.lng));
  }, [visible, map]);

  // 접속하자마자 내 위치(거부/미지원이면 기본 중심) 주변의 추천 매장을 보여준다.
  // searched가 켜지면 아래 effect가 centerRef 기준으로 로드하고, 이후 등급 기준
  // 변경 시 같은 중심으로 refetch한다. 등급 온오프는 refetch 없이 클라이언트
  // 필터링 -- see visibleStores.
  const [searched, setSearched] = useState(false);
  useEffect(() => {
    if (!ready) return;
    if (!navigator.geolocation) {
      setSearched(true);
      return;
    }
    setStatus("내 위치 확인 중...");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        centerRef.current = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        map.setCenter(new window.kakao.maps.LatLng(pos.coords.latitude, pos.coords.longitude));
        setSearched(true);
      },
      () => setSearched(true) // 권한 거부 -> 기본 중심(서울시청) 주변으로라도 보여준다.
    );
  }, [ready]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!ready || !searched) return;
    loadStores(centerRef.current.lat, centerRef.current.lng);
  }, [ready, searched, gradeType]); // eslint-disable-line react-hooks/exhaustive-deps

  // Draw pins for whatever store list is current.
  useEffect(() => {
    if (!ready || !map) return;
    overlaysRef.current.forEach((o) => o.setMap(null));
    overlaysRef.current = [];

    visibleStores.forEach((store) => {
      const displayGrade = gradeType === "absolute" ? store.absolute_grade : store.relative_grade;
      const el = document.createElement("div");
      el.className = "map-pin";
      el.style.background = GRADE_COLOR[displayGrade] ?? "#999";
      el.innerHTML = `<span>${store.restaurant_name}</span>`;
      el.addEventListener("click", () => showPopup(store));

      const overlay = new window.kakao.maps.CustomOverlay({
        position: new window.kakao.maps.LatLng(store.lat, store.lng),
        content: el,
        yAnchor: 1,
      });
      overlay.setMap(map);
      overlaysRef.current.push(overlay);
    });
  }, [visibleStores, ready, map, gradeType, showPopup]);

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
      setSearched(true);
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
        setSearched(true);
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
    <section className="map-view">
      <div className="map-toolbar">
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
          <span className="filter-label">등급 표시</span>
          {ALL_GRADES.map((g) => (
            <button
              key={g}
              className={`grade-toggle-btn ${activeGrades.has(g) ? "active" : "off"}`}
              style={activeGrades.has(g) ? { background: GRADE_COLOR[g], borderColor: GRADE_COLOR[g] } : undefined}
              onClick={() => toggleGrade(g)}
            >
              {g}
            </button>
          ))}
        </div>
        </div>
        <span className="map-status">{sdkError ?? status}</span>
      </div>

      <div className="map-layout">
        <div id="map-container" ref={containerRef} />
        <div className="store-list">
          {!searched && !sdkError && (
            <p className="store-list-empty">
              지역을 검색하거나 <b>내 위치</b>를 눌러 주변 매장을 불러오세요.
            </p>
          )}
          {visibleStores.map((store) => {
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
          <div className="map-legend">
            {ALL_GRADES.map((g) => (
              <span key={g}>
                <span className={`grade-badge ${GRADE_CLASS[g]}`}>{g}</span>등급
              </span>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
