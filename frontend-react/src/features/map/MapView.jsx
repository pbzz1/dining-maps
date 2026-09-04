import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { track } from "../../constants";
import { fetchStores } from "../../api";
import { useKakaoMap } from "./useKakaoMap";
import {
  DEFAULT_CENTER, SEARCH_RADIUS_M, GRADE_COLOR, GRADE_CLASS, GRADE_RANK, ALL_GRADES, BRAND_SLUGS, formatDistance,
} from "../../constants";


// 주변 매장 전부가 아니라 "다이어트로 그나마 추천할 만한" 상위 N곳만 보여준다.
// 기본값일 뿐 -- 사용자가 툴바에서 바꿀 수 있다 (LIMIT_OPTIONS/RADIUS_OPTIONS).
const RECOMMEND_LIMIT = 15;

// 지도를 축소하면 핀들이 서로 겹쳐 아무것도 못 읽게 된다. 화면상 이 픽셀 격자
// 안에 들어오는 핀들은 "N곳" 요약 하나로 묶는다 (클릭하면 그 자리로 확대).
const CLUSTER_PX = 48;

// 등급 글자만 있는 핀은 "여기가 어느 브랜드인지"를 아무것도 말해주지 않는다.
// 목록 카드와 같은 로고 타일을 핀 안에도 넣는다 (없는 브랜드는 첫 글자로 폴백).
function brandTile(name) {
  const tile = document.createElement("span");
  tile.className = "pin-logo";
  const slug = BRAND_SLUGS[name];
  if (!slug) {
    tile.textContent = name.charAt(0);
    return tile;
  }
  const img = document.createElement("img");
  img.src = `/logos/${slug}.png`;
  img.alt = "";
  img.addEventListener("error", () => { tile.textContent = name.charAt(0); });
  tile.appendChild(img);
  return tile;
}
const LIMIT_OPTIONS = [10, 15, 20, 30];
const RADIUS_OPTIONS = [
  { value: 1000, label: "1km" },
  { value: 3000, label: "3km" },
  { value: 5000, label: "5km" },
  { value: 10000, label: "10km" },
  { value: 30000, label: "30km" },
];

export default function MapView({ onOpenMenu, visible = true }) {
  const containerRef = useRef(null);
  const overlaysRef = useRef([]);
  const popupRef = useRef(null);
  const centerRef = useRef(DEFAULT_CENTER);
  const myLocRef = useRef(null); // 현 위치 파란 점 -- 매장 핀과 별개로 유지
  const pinsRef = useRef(new Map()); // store.id -> { el, overlay, baseZ } : 선택 강조용
  const selectedIdRef = useRef(null); // 줌으로 핀을 다시 그려도 선택 상태를 잃지 않게

  const { map, places, ready, error: sdkError } = useKakaoMap(containerRef, DEFAULT_CENTER);

  const [stores, setStores] = useState([]);
  const [status, setStatus] = useState("");
  const [gradeType, setGradeType] = useState("relative");
  const [activeGrades, setActiveGrades] = useState(() => new Set(ALL_GRADES));
  const [keyword, setKeyword] = useState("");
  const [radiusM, setRadiusM] = useState(SEARCH_RADIUS_M);
  const [limit, setLimit] = useState(RECOMMEND_LIMIT);
  // 목록↔지도 호버 연동의 단일 출처. 어느 쪽에 커서를 올려도 여기로 모인다.
  const [hoverId, setHoverId] = useState(null);

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
      .slice(0, limit);
  }, [stores, gradeType, activeGrades, limit]);

  const clearOverlays = useCallback(() => {
    overlaysRef.current.forEach((o) => o.setMap(null));
    overlaysRef.current = [];
    if (popupRef.current) {
      popupRef.current.setMap(null);
      popupRef.current = null;
    }
  }, []);

  // 어느 핀을 보고 있는지 지도 위에서도 알 수 있게 -- 선택된 핀만 이름을 펼친 채 둔다.
  const highlightPin = useCallback((id) => {
    selectedIdRef.current = id;
    for (const [sid, pin] of pinsRef.current) {
      const on = sid === id;
      pin.el.classList.toggle("is-selected", on);
      pin.overlay.setZIndex(on ? 190000 : pin.baseZ);
    }
  }, []);

  const showPopup = useCallback(
    (store) => {
      if (popupRef.current) popupRef.current.setMap(null);
      highlightPin(store.id);
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
      el.addEventListener("click", (ev) => ev.stopPropagation()); // 팝업 안 클릭으로는 안 닫힘
      el.querySelector(".store-popup-close").addEventListener("click", () => {
        popupRef.current?.setMap(null);
        popupRef.current = null;
        highlightPin(null);
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

      // 화면 가장자리 매장을 누르면 팝업이 지도 밖으로 잘린다(특히 위쪽 -- 팝업이
      // 핀 위로 열리니까). 실제로 그려진 팝업 상자와 지도 상자를 재서 삐져나온
      // 만큼만 지도를 민다. 좌표 계산 대신 실측이라 앵커·여백이 바뀌어도 맞는다.
      const M = 12; // 좌우·아래 여백
      const M_TOP = 56; // 위쪽은 등급 범례 띠까지 피한다
      const nudgeIntoView = () => {
        if (popupRef.current !== overlay || !containerRef.current) return 0;
        const box = containerRef.current.getBoundingClientRect();
        const p = el.getBoundingClientRect();
        if (!p.height) return 0;
        let dx = 0;
        let dy = 0;
        if (p.top < box.top + M_TOP) dy = p.top - (box.top + M_TOP);
        else if (p.bottom > box.bottom - M) dy = p.bottom - (box.bottom - M);
        if (p.right > box.right - M) dx = p.right - (box.right - M);
        else if (p.left < box.left + M) dx = p.left - (box.left + M);
        if (dx || dy) map.panBy(dx, dy);
        return Math.abs(dx) + Math.abs(dy);
      };
      // panBy는 애니메이션이라 한 번에 딱 맞지 않을 수 있다 -- 남은 만큼 한 번 더.
      requestAnimationFrame(() => {
        if (nudgeIntoView()) setTimeout(nudgeIntoView, 400);
      });
    },
    [map, onOpenMenu, highlightPin]
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
        // 매장 핀(호버 200000)보다 항상 위 -- 핀에 가려 내 위치를 잃어버리지
        // 않도록. 팝업(300000)만 이보다 앞에 온다.
        zIndex: 250000,
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
        const params = { lat, lng, radius_m: radiusM, grade_type: gradeType };
        const list = await fetchStores(params);
        setStores(list);
        setStatus(
          list.length === 0
            ? "주변에 매장이 없습니다."
            : `주변 매장 ${list.length}곳 중 다이어트 추천 상위 ${Math.min(limit, new Set(list.map((s) => s.restaurant_id)).size)}곳`
        );
      } catch (e) {
        setStatus(`매장 정보를 불러오지 못했습니다: ${e.message}`);
      }
    },
    [gradeType, radiusM, limit, clearOverlays]
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
  }, [ready, searched, gradeType, radiusM]); // eslint-disable-line react-hooks/exhaustive-deps

  // 클러스터링은 현재 줌 레벨의 화면 좌표 기준이라, 레벨이 바뀌면 다시 묶어야 한다.
  const [level, setLevel] = useState(null);
  useEffect(() => {
    if (!ready || !map) return;
    const sync = () => setLevel(map.getLevel());
    window.kakao.maps.event.addListener(map, "zoom_changed", sync);
    sync();
    return () => window.kakao.maps.event.removeListener(map, "zoom_changed", sync);
  }, [ready, map]);

  // Draw pins for whatever store list is current.
  useEffect(() => {
    if (!ready || !map) return;
    overlaysRef.current.forEach((o) => o.setMap(null));
    overlaysRef.current = [];
    pinsRef.current = new Map();

    // 화면 좌표(현재 레벨 기준)로 격자에 담아, 같은 칸에 2곳 이상이면 요약 핀 하나로.
    const proj = map.getProjection();
    const cells = new Map();
    visibleStores.forEach((store, rank) => {
      if (rank < 3) return; // 추천 상위 3곳은 항상 개별 핀으로 남긴다
      const pt = proj.pointFromCoords(new window.kakao.maps.LatLng(store.lat, store.lng));
      const key = `${Math.floor(pt.x / CLUSTER_PX)},${Math.floor(pt.y / CLUSTER_PX)}`;
      if (!cells.has(key)) cells.set(key, []);
      cells.get(key).push({ store, rank });
    });

    visibleStores.slice(0, 3).forEach((store, rank) => drawPin(store, rank));

    for (const group of cells.values()) {
      if (group.length > 1) {
        drawCluster(group);
        continue;
      }
      drawPin(group[0].store, group[0].rank);
    }

    // 묶인 핀들: 대표(추천 순위가 가장 높은) 매장의 등급 색 + 개수만 보여준다.
    function drawCluster(group) {
      const lead = group[0].store; // visibleStores 순서를 유지하므로 첫 원소가 최상위
      const grade = gradeType === "absolute" ? lead.absolute_grade : lead.relative_grade;
      const lat = group.reduce((a, g) => a + g.store.lat, 0) / group.length;
      const lng = group.reduce((a, g) => a + g.store.lng, 0) / group.length;
      const el = document.createElement("div");
      el.className = "map-cluster";
      el.style.background = GRADE_COLOR[grade] ?? "#999";
      el.title = group.map((g) => `${g.store.restaurant_name} ${g.store.branch_name ?? ""}`).join(" / ");
      el.innerHTML = `<b>${group.length}</b><span>곳</span>`;
      const pos = new window.kakao.maps.LatLng(lat, lng);
      // 클릭하면 그 자리를 두 단계 확대 -- 확대하면 격자가 풀려 개별 핀으로 나뉜다.
      el.addEventListener("click", (ev) => {
        ev.stopPropagation();
        map.setLevel(Math.max(1, map.getLevel() - 2), { animate: true, anchor: pos });
      });
      const overlay = new window.kakao.maps.CustomOverlay({
        position: pos,
        content: el,
        yAnchor: 1,
        zIndex: 90000, // 상위 3곳 핀(100000+)보다는 뒤
      });
      overlay.setMap(map);
      overlaysRef.current.push(overlay);
    }

    // visibleStores는 이미 추천순 정렬 -- 앞 3곳만 순위를 달아 크게 강조한다.
    function drawPin(store, rank) {
      const displayGrade = gradeType === "absolute" ? store.absolute_grade : store.relative_grade;
      const isTop = rank < 3;
      const isSelected = selectedIdRef.current === store.id;
      const el = document.createElement("div");
      el.className = `map-pin${isTop ? " map-pin-top" : ""}${isSelected ? " is-selected" : ""}`;
      el.style.background = GRADE_COLOR[displayGrade] ?? "#999";
      el.innerHTML =
        (isTop ? `<em class="pin-rank">${rank + 1}</em>` : "") +
        `<b class="pin-grade">${displayGrade ?? "?"}</b>` +
        `<span class="pin-name">${store.restaurant_name}</span>`;
      el.insertBefore(brandTile(store.restaurant_name), el.querySelector(".pin-grade"));
      el.title = `${store.restaurant_name} ${store.branch_name ?? ""}`;
      el.addEventListener("click", (ev) => {
        ev.stopPropagation(); // 지도 클릭(=팝업 닫기)까지 같이 타지 않게
        showPopup(store);
      });

      // 겹칠 때 아래 핀의 글자가 위 핀 뒤로 삐져나와 보이는 문제:
      // 화면상 아래(남쪽)에 있는 핀이 위에 오도록 위도 기반으로 쌓아
      // 자연스러운 층으로 보이게 하고, 상위 3곳은 항상 그 위에 둔다.
      const baseZ = isTop ? 100000 + (3 - rank) : Math.round((90 - store.lat) * 1000);
      const overlay = new window.kakao.maps.CustomOverlay({
        position: new window.kakao.maps.LatLng(store.lat, store.lng),
        content: el,
        yAnchor: 1,
        zIndex: isSelected ? 190000 : baseZ,
      });
      el.addEventListener("mouseenter", () => setHoverId(store.id));
      el.addEventListener("mouseleave", () => setHoverId(null));
      overlay.setMap(map);
      overlaysRef.current.push(overlay);
      pinsRef.current.set(store.id, { el, overlay, baseZ });
    }
  }, [visibleStores, ready, map, gradeType, showPopup, level]);

  // 지도의 빈 곳을 누르면 열려 있던 매장 팝업을 닫는다 (닫기 버튼만으로는 답답하다).
  useEffect(() => {
    if (!ready || !map) return;
    const close = () => {
      if (!popupRef.current) return;
      popupRef.current.setMap(null);
      popupRef.current = null;
      highlightPin(null);
    };
    window.kakao.maps.event.addListener(map, "click", close);
    return () => window.kakao.maps.event.removeListener(map, "click", close);
  }, [ready, map, highlightPin]);

  // 호버한 핀은 이름을 펼치고 맨 앞으로 -- 가려진 핀도 커서만 대면 전체가 보인다.
  useEffect(() => {
    for (const [id, pin] of pinsRef.current) {
      const on = id === hoverId;
      pin.el.classList.toggle("is-hover", on);
      if (on) pin.overlay.setZIndex(200000);
      else if (!pin.el.classList.contains("is-selected")) pin.overlay.setZIndex(pin.baseZ);
    }
  }, [hoverId, visibleStores, level]);

  // 옵션 없이 keywordSearch를 부르면 카카오가 전국 기준으로 정렬해
  // "커피"류 일반 검색어가 늘 서울에서 잡혔다. 현재 중심 반경 안을 먼저 보고,
  // 결과가 없으면(= 다른 지역 이름을 친 경우) 전국 검색으로 폴백한다.
  function handleSearch() {
    const q = keyword.trim();
    if (!q || !places) return;
    setStatus("검색 중...");

    // 매장 이름을 친 경우 -- 이미 불러온 반경 안 매장 중 가장 가까운 곳을 고른다.
    // 지역 검색으로 넘기면 반경 밖 동명 지점(예: 다른 동네 스타벅스)으로 튀어버린다.
    const hit = stores
      .filter((s) => `${s.restaurant_name} ${s.branch_name ?? ""}`.toLowerCase().includes(q.toLowerCase()))
      .sort((a, b) => (a.distance_m ?? Infinity) - (b.distance_m ?? Infinity))[0];
    if (hit) {
      setStatus(`반경 내 "${q}" 최근접 매장: ${hit.restaurant_name} ${hit.branch_name ?? ""}`);
      focusStore(hit);
      return;
    }

    const { Status, SortBy } = window.kakao.maps.services;
    const goTo = (place) => {
      const lat = parseFloat(place.y);
      const lng = parseFloat(place.x);
      map.panTo(new window.kakao.maps.LatLng(lat, lng));
      setSearched(true);
      loadStores(lat, lng);
    };
    places.keywordSearch(
      q,
      (data, s) => {
        if (s === Status.OK && data.length > 0) return goTo(data[0]);
        places.keywordSearch(q, (all, s2) => {
          if (s2 !== Status.OK || all.length === 0) {
            setStatus(`"${q}" 검색 결과가 없습니다.`);
            return;
          }
          goTo(all[0]);
        });
      },
      {
        location: new window.kakao.maps.LatLng(centerRef.current.lat, centerRef.current.lng),
        radius: Math.min(radiusM, 20000), // 20km가 카카오 허용 최대치
        sort: SortBy.DISTANCE,
      }
    );
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
        map.panTo(new window.kakao.maps.LatLng(latitude, longitude));
        showMyLocation(latitude, longitude);
        setSearched(true);
        loadStores(latitude, longitude);
      },
      () => setStatus("위치 권한이 거부되었습니다.")
    );
  }

  // 목록에서 고른 매장으로 "뚝" 튀지 않고 부드럽게 이동한다.
  // 확대와 이동 애니메이션을 동시에 걸면 panTo가 확대 전 좌표로 거리를 재서
  // 엉뚱한 곳(2km 밖)에 멈춘다. 확대는 대상 지점을 고정점(anchor)으로 즉시 끝내고
  // 남은 거리만 panTo로 부드럽게 이동한다.
  function focusStore(store) {
    const pos = new window.kakao.maps.LatLng(store.lat, store.lng);
    if (map.getLevel() !== 3) map.setLevel(3, { anchor: pos });
    map.panTo(pos);
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
          <button className="btn-search" onClick={() => { track("map_search", { keyword }); handleSearch(); }}>검색</button>
          <button onClick={() => { track("map_locate"); handleLocate(); }}>내 위치</button>
        </div>

        <div className="filter-controls">
          <div className="filter-group">
            <span className="filter-label">검색 반경</span>
            <div className="grade-mode-toggle" role="group" aria-label="검색 반경">
              {RADIUS_OPTIONS.map((r) => (
                <button
                  key={r.value}
                  className={radiusM === r.value ? "active" : ""}
                  onClick={() => { track("map_radius", { radius_m: r.value }); setRadiusM(r.value); }}
                >
                  {r.label}
                </button>
              ))}
            </div>
          </div>
          <div className="filter-group">
            <span className="filter-label">추천 개수</span>
            <select
              className="map-select"
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
              aria-label="표시할 추천 매장 개수"
            >
              {LIMIT_OPTIONS.map((n) => (
                <option key={n} value={n}>{n}곳</option>
              ))}
            </select>
          </div>
          <div className="grade-mode-toggle" role="group" aria-label="등급 기준 선택">
            {["relative", "absolute"].map((t) => (
              <button
                key={t}
                className={gradeType === t ? "active" : ""}
                onClick={() => { track("map_grade_type", { type: t }); setGradeType(t); }}
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
                onClick={() => { track("map_grade_filter", { grade: g }); toggleGrade(g); }}
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
            <em className="pin-rank">1</em>
            골드 = 다이어트 추천 상위 3곳
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
              <div
                key={store.id}
                className={`store-card${hoverId === store.id ? " is-hover" : ""}`}
                onMouseEnter={() => setHoverId(store.id)}
                onMouseLeave={() => setHoverId(null)}
                onClick={() => { track("map_store_focus", { name: store.name }); focusStore(store); }}>
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
