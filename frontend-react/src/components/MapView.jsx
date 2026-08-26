import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchStores } from "../api";
import { useKakaoMap } from "../useKakaoMap";
import {
  DEFAULT_CENTER, SEARCH_RADIUS_M, GRADE_COLOR, GRADE_CLASS, GRADE_RANK, ALL_GRADES, formatDistance,
} from "../constants";

// 추천 TOP 3 왕관 (범례 설명과 핀 장식에 공용)
const CROWN_PATH = "M3.5 8.5 L8 12 L12 5.5 L16 12 L20.5 8.5 L18.5 17.5 Q12 19 5.5 17.5 Z";
const CROWN_SVG = `<svg class="pin-crown" width="24" height="24" viewBox="0 0 24 24"><path d="${CROWN_PATH}" fill="#FFC53D" stroke="#B8860B" stroke-width="1.2" stroke-linejoin="round"></path></svg>`;

// 주변 매장 전부가 아니라 "다이어트로 그나마 추천할 만한" 상위 N곳만 보여준다.
const RECOMMEND_LIMIT = 15;

export default function MapView({ onOpenMenu, visible = true }) {
  const containerRef = useRef(null);
  const overlaysRef = useRef([]);
  const popupRef = useRef(null);
  const centerRef = useRef(DEFAULT_CENTER);
  const myLocRef = useRef(null); // 현 위치 파란 점 -- 매장 핀과 별개로 유지

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
        ${store.reco_menu ? `<div class="store-reco">🤖 <b>${store.reco_menu}</b><span>${store.reco_reason ?? ""}</span></div>` : ""}
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
        zIndex: 300000, // 호버로 끌어올린 핀(200000)보다도 항상 위
      });
      overlay.setMap(map);
      popupRef.current = overlay;
    },
    [map, onOpenMenu]
  );

  // 실제 위치 파악에 성공했을 때만 호출된다 -- 기본 중심(서울시청) 폴백에는
  // 점을 찍지 않는다. 거기 있지 않은 사용자에게 거짓 위치를 보여주게 되니까.
  const showMyLocation = useCallback(
    (lat, lng) => {
      if (myLocRef.current) myLocRef.current.setMap(null);
      const el = document.createElement("div");
      el.className = "my-location";
      el.innerHTML = `<span class="my-location-pulse"></span><span class="my-location-dot"></span>`;
      myLocRef.current = new window.kakao.maps.CustomOverlay({
        position: new window.kakao.maps.LatLng(lat, lng),
        content: el,
        yAnchor: 0.5,
        zIndex: 2,
      });
      myLocRef.current.setMap(map);
    },
    [map]
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
        showMyLocation(pos.coords.latitude, pos.coords.longitude);
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

    // visibleStores는 이미 추천순 정렬 -- 앞 3곳만 순위를 달아 크게 강조한다.
    visibleStores.forEach((store, rank) => {
      const displayGrade = gradeType === "absolute" ? store.absolute_grade : store.relative_grade;
      const isTop = rank < 3;
      const el = document.createElement("div");
      el.className = `map-pin${isTop ? " map-pin-top" : ""}`;
      el.style.background = GRADE_COLOR[displayGrade] ?? "#999";
      el.innerHTML =
        (isTop ? `${CROWN_SVG}<em class="pin-rank">${rank + 1}</em>` : "") +
        `<b class="pin-grade">${displayGrade ?? "?"}</b><span>${store.restaurant_name}</span>`;
      el.addEventListener("click", () => showPopup(store));

      // 겹칠 때 아래 핀의 글자가 위 핀 뒤로 삐져나와 보이는 문제:
      // 화면상 아래(남쪽)에 있는 핀이 위에 오도록 위도 기반으로 쌓아
      // 자연스러운 층으로 보이게 하고, 상위 3곳은 항상 그 위에 둔다.
      const baseZ = isTop ? 100000 + (3 - rank) : Math.round((90 - store.lat) * 1000);
      const overlay = new window.kakao.maps.CustomOverlay({
        position: new window.kakao.maps.LatLng(store.lat, store.lng),
        content: el,
        yAnchor: 1,
        zIndex: baseZ,
      });
      // 호버한 핀은 맨 앞으로 -- 가려진 핀도 커서만 대면 전체가 보인다.
      el.addEventListener("mouseenter", () => overlay.setZIndex(200000));
      el.addEventListener("mouseleave", () => overlay.setZIndex(baseZ));
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
        showMyLocation(latitude, longitude);
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
            type="search"
            placeholder="지역/주소 검색 (예: 강남역)"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          />
          <button className="btn-search" onClick={handleSearch}>검색</button>
          <button onClick={handleLocate}>내 위치</button>
        </div>

        <div className="filter-controls">
          <div className="grade-mode-toggle" role="group" aria-label="등급 기준 선택">
            {["relative", "absolute"].map((t) => (
              <button
                key={t}
                className={gradeType === t ? "active" : ""}
                onClick={() => setGradeType(t)}
              >
                {t === "relative" ? "상대 기준" : "절대 기준(WHO)"}
              </button>
            ))}
          </div>
          <div className="filter-group" role="group" aria-label="표시할 등급">
            <span className="filter-label">등급</span>
            {ALL_GRADES.map((g) => (
              <button
                key={g}
                className={`grade-toggle-btn ${activeGrades.has(g) ? "active" : "off"}`}
                style={activeGrades.has(g) ? { background: GRADE_COLOR[g], borderColor: GRADE_COLOR[g] } : undefined}
                onClick={() => toggleGrade(g)}
                title={`${g}등급 ${activeGrades.has(g) ? "숨기기" : "표시"}`}
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
        {/* 등급 색의 의미를 첫 화면에서 바로 알 수 있게 지도 위에 상시 표시 */}
        <div className="map-grade-legend" aria-hidden="true">
          {ALL_GRADES.map((g) => (
            <span key={g}>
              <i style={{ background: GRADE_COLOR[g] }} />
              {g} {{ A: "아주 좋음", B: "좋음", C: "보통", D: "주의" }[g]}
            </span>
          ))}
          <span className="legend-divider" />
          <span>
            <svg width="16" height="16" viewBox="0 0 24 24">
              <path d={CROWN_PATH} fill="#FFC53D" stroke="#B8860B" strokeWidth="1.2" strokeLinejoin="round" />
            </svg>
            1·2·3 = 다이어트 추천 순위
          </span>
        </div>
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
                {store.reco_menu && (
                  <div className="store-reco">
                    🤖 <b>{store.reco_menu}</b>
                    <span>{store.reco_reason}</span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
