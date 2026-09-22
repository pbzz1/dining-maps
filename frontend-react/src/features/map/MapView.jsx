import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { track } from "../../constants";
import { fetchStores, fetchBrandReco } from "../../api";
import { useKakaoMap } from "./useKakaoMap";
import {
  DEFAULT_CENTER, SEARCH_RADIUS_M, GRADE_COLOR, GRADE_CLASS, GRADE_RANK, ALL_GRADES, BRAND_SLUGS,
  MAP_GOALS, MAP_CATEGORIES, formatDistance,
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
  // 무엇을 먹을지(목표·음식 종류). 이 두 개가 추천 순서를 바꾸는 축이다 -- 없을 때는
  // 브랜드 평균 등급 하나로만 줄을 세워서, 어느 동네에서 열어도 같은 브랜드가 1~3위였다.
  const [goal, setGoal] = useState("diet");
  const [category, setCategory] = useState(null); // null = 전체
  const [reco, setReco] = useState(new Map()); // restaurant_id -> 그 목표·종류의 추천 메뉴
  // 우리가 영양정보를 가진 16개 브랜드 밖의 식당들. 카카오 장소 검색(FD6)으로 그 자리에서
  // 채우고, 영양정보가 없다는 걸 화면에서 분명히 밝힌 채로만 보여준다.
  const [showNearby, setShowNearby] = useState(false);
  const [nearby, setNearby] = useState([]);
  const [centerKey, setCenterKey] = useState(""); // 중심이 바뀌면 주변 식당도 다시 받는다
  const nearbyOverlaysRef = useRef([]);
  // 목록↔지도 호버 연동의 단일 출처. 어느 쪽에 커서를 올려도 여기로 모인다.
  const [hoverId, setHoverId] = useState(null);

  // 목표/종류가 바뀌면 이것만 다시 받는다 -- 브랜드 수만큼이라 작고, 반경 안 매장
  // 목록은 그대로 두니 화면이 즉시 다시 정렬된다.
  useEffect(() => {
    let alive = true;
    fetchBrandReco(category ? { goal, category } : { goal })
      .then((rows) => alive && setReco(new Map(rows.map((r) => [r.restaurant_id, r]))))
      .catch(() => alive && setReco(new Map()));
    return () => { alive = false; };
  }, [goal, category]);

  function toggleGrade(g) {
    setActiveGrades((prev) => {
      const next = new Set(prev);
      next.has(g) ? next.delete(g) : next.add(g);
      return next;
    });
  }

  // A/B/C/D 온오프는 클라이언트에서 필터링한다 -- /api/stores의 min_grade는
  // "이 등급 이상"만 지원해서 서버에서 임의 조합(예: A,C만 켜기)을 걸 수 없다.
  // 그 다음 브랜드당 최근접 매장 1곳으로 추리고(같은 브랜드 지점 15개를 "추천"이라고
  // 줄세우지 않기 위해), 아래 점수로 상위 N곳만 남긴다.
  const visibleStores = useMemo(() => {
    const gradeOf = (s) => (gradeType === "absolute" ? s.absolute_grade : s.relative_grade);
    const nearestPerBrand = new Map();
    for (const s of stores) {
      const g = gradeOf(s);
      if (g != null && !activeGrades.has(g)) continue;
      // 음식 종류를 골랐으면 그 종류 메뉴가 있는 브랜드만 남긴다 -- "버거"를 고른
      // 사람에게 커피 브랜드를 추천 1위로 내밀지 않기 위해.
      if (category && !reco.has(s.restaurant_id)) continue;
      const prev = nearestPerBrand.get(s.restaurant_id);
      if (!prev || (s.distance_m ?? Infinity) < (prev.distance_m ?? Infinity)) {
        nearestPerBrand.set(s.restaurant_id, s);
      }
    }
    // 추천 점수 = 목표 적합도 60% + 가까움 40%.
    // 등급만으로 정렬하면 순위가 브랜드 고정값이라 어디서 열어도 같은 줄이 나온다.
    // 목표(다이어트/근성장/저나트륨)와 실제 거리가 함께 순위를 만들도록 섞는다.
    const GRADE_FIT = { A: 0.75, B: 0.5, C: 0.25, D: 0 };
    const scoreOf = (s) => {
      const r = reco.get(s.restaurant_id);
      // 목표 기준으로 추천할 메뉴를 못 찾은 브랜드(영양정보 결측)는 등급으로 대신하되,
      // 근거가 약하므로 같은 등급의 추천 가능 브랜드보다 앞에 서지 못하게 낮춰 잡는다.
      const fit = r ? r.rank : (GRADE_FIT[gradeOf(s)] ?? 0) * 0.6;
      const near = 1 - Math.min(s.distance_m ?? radiusM, radiusM) / radiusM;
      return fit * 0.6 + near * 0.4;
    };
    return [...nearestPerBrand.values()]
      .sort((a, b) => scoreOf(b) - scoreOf(a) || (a.distance_m ?? 0) - (b.distance_m ?? 0))
      .slice(0, limit);
  }, [stores, gradeType, activeGrades, limit, reco, category, radiusM]);

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
      // 선택한 목표·종류로 계산한 추천 메뉴가 우선. 없으면 기존 LLM 고정 추천으로 폴백.
      const pick = reco.get(store.restaurant_id);
      const recoMenu = pick?.menu_name ?? store.reco_menu;
      const recoReason = pick?.reason ?? store.reco_reason ?? "";

      const el = document.createElement("div");
      el.className = "store-popup";
      el.innerHTML = `
        <button class="store-popup-close" type="button">&times;</button>
        <div class="store-popup-title">${store.restaurant_name} ${store.branch_name}</div>
        <div class="store-popup-meta">절대 ${store.absolute_grade ?? "-"} · 상대 ${store.relative_grade ?? "-"} · 도움 메뉴 ${ratio}</div>
        <div class="store-popup-meta">${formatDistance(store.distance_m)}${store.address ? " · " + store.address : ""}</div>
        ${recoMenu ? `<div class="store-reco"><b>${recoMenu}</b><span>${recoReason}</span></div>` : ""}
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

      // 팝업은 핀 위로 열려서, 지도 위쪽 매장을 누르면 머리가 잘려 나간다.
      // 지도를 움직여 맞추는 대신(panBy는 팝업도 같이 끌고 다녀 잘 맞지 않는다)
      // 자리가 없으면 팝업을 핀 아래로 뒤집고, 좌우도 넘친 만큼만 밀어 넣는다.
      requestAnimationFrame(() => {
        if (popupRef.current !== overlay || !containerRef.current) return;
        const box = containerRef.current.getBoundingClientRect();
        const r = el.getBoundingClientRect();
        if (!r.height) return;
        const M = 12; // 좌우 여백
        const M_TOP = 56; // 위쪽은 등급 범례 띠까지 피한다
        let dx = 0;
        let dy = 0;
        if (r.top < box.top + M_TOP) dy = r.height + 26; // 핀 아래로 뒤집기
        if (r.right > box.right - M) dx = box.right - M - r.right;
        else if (r.left < box.left + M) dx = box.left + M - r.left;
        if (dx || dy) el.style.transform = `translate(${dx}px, ${dy}px)`;
      });
    },
    [map, onOpenMenu, highlightPin, reco]
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
      setCenterKey(`${lat},${lng}`);
      setStatus("매장 불러오는 중...");
      clearOverlays();
      try {
        const params = { lat, lng, radius_m: radiusM, grade_type: gradeType };
        const list = await fetchStores(params);
        setStores(list);
        setStatus(list.length === 0 ? "주변에 매장이 없습니다." : "");
      } catch (e) {
        setStatus(`매장 정보를 불러오지 못했습니다: ${e.message}`);
      }
    },
    [gradeType, radiusM, clearOverlays]
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
      el.style.setProperty("--pin-color", GRADE_COLOR[grade] ?? "#999");
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
      el.style.setProperty("--pin-color", GRADE_COLOR[displayGrade] ?? "#999");
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

  // --- 영양정보가 없는 주변 식당 (카카오 장소 검색) ---
  //
  // 우리가 영양정보를 가진 브랜드는 16곳뿐이라, 그 밖의 식당은 지도에서 아예 존재하지
  // 않는 것처럼 보였다. 밥집 자체는 카카오가 알고 있으니 그 자리에서 받아와 "여기도
  // 식당이 있다"까지는 보여주고, 영양정보가 없다는 사실은 숨기지 않는다.
  useEffect(() => {
    if (!showNearby) {
      setNearby([]);
      return;
    }
    if (!ready || !places) return;
    const { lat, lng } = centerRef.current;
    let alive = true;
    const { Status, SortBy } = window.kakao.maps.services;
    const brands = Object.keys(BRAND_SLUGS);
    places.categorySearch(
      "FD6",
      (data, status) => {
        if (!alive) return;
        if (status !== Status.OK) {
          setNearby([]);
          return;
        }
        // 이미 등급 핀이 꽂힌 프랜차이즈는 빼고 -- 같은 매장이 두 번 보이면 등급 있는
        // 핀과 없는 핀이 나란히 서서 어느 쪽을 믿어야 할지 알 수 없게 된다.
        setNearby(data.filter((pl) => !brands.some((b) => pl.place_name.includes(b))));
      },
      {
        location: new window.kakao.maps.LatLng(lat, lng),
        radius: Math.min(radiusM, 20000), // 20km가 카카오 허용 최대치
        size: 15,
        sort: SortBy.DISTANCE,
      }
    );
    return () => { alive = false; };
  }, [showNearby, ready, places, radiusM, centerKey]);

  const showNearbyPopup = useCallback(
    (place) => {
      if (popupRef.current) popupRef.current.setMap(null);
      const el = document.createElement("div");
      el.className = "store-popup";
      el.innerHTML = `
        <button class="store-popup-close" type="button">&times;</button>
        <div class="store-popup-title">${place.place_name}</div>
        <div class="store-popup-meta">${place.category_name ?? ""}</div>
        <div class="store-popup-meta">${formatDistance(Number(place.distance))}${place.road_address_name ? " · " + place.road_address_name : ""}</div>
        <div class="store-nodata">영양정보 없음 — 등급을 매길 근거가 없습니다.</div>
        <a class="store-popup-menu-btn" href="${place.place_url}" target="_blank" rel="noreferrer">카카오맵에서 보기</a>
      `;
      el.addEventListener("click", (ev) => ev.stopPropagation());
      el.querySelector(".store-popup-close").addEventListener("click", () => {
        popupRef.current?.setMap(null);
        popupRef.current = null;
      });
      const overlay = new window.kakao.maps.CustomOverlay({
        position: new window.kakao.maps.LatLng(Number(place.y), Number(place.x)),
        content: el,
        yAnchor: 1.4,
        zIndex: 300000,
      });
      overlay.setMap(map);
      popupRef.current = overlay;
    },
    [map]
  );

  useEffect(() => {
    if (!ready || !map) return;
    nearbyOverlaysRef.current.forEach((o) => o.setMap(null));
    nearbyOverlaysRef.current = [];
    for (const place of nearby) {
      const el = document.createElement("div");
      el.className = "map-pin map-pin-plain";
      el.innerHTML = `<span class="pin-name">${place.place_name}</span>`;
      el.title = `${place.place_name} (영양정보 없음)`;
      el.addEventListener("click", (ev) => {
        ev.stopPropagation();
        showNearbyPopup(place);
      });
      const overlay = new window.kakao.maps.CustomOverlay({
        position: new window.kakao.maps.LatLng(Number(place.y), Number(place.x)),
        content: el,
        yAnchor: 1,
        zIndex: 1000, // 등급 있는 추천 핀보다 항상 뒤
      });
      overlay.setMap(map);
      nearbyOverlaysRef.current.push(overlay);
    }
  }, [nearby, ready, map, showNearbyPopup]);

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

        {/* 무엇을 먹을지부터 고르게 한다 -- 등급 필터는 그 다음 문제다. */}
        <div className="goal-controls">
          <div className="filter-group">
            <span className="filter-label">목표</span>
            <div className="chip-row" role="group" aria-label="추천 목표">
              {MAP_GOALS.map((g) => (
                <button
                  key={g.key}
                  className={`chip${goal === g.key ? " active" : ""}`}
                  title={g.hint}
                  onClick={() => { track("map_goal", { goal: g.key }); setGoal(g.key); }}
                >
                  {g.label}
                </button>
              ))}
            </div>
          </div>
          <div className="filter-group">
            <span className="filter-label">먹고 싶은 것</span>
            <div className="chip-row" role="group" aria-label="음식 종류">
              <button
                className={`chip${category === null ? " active" : ""}`}
                onClick={() => { track("map_category", { category: "전체" }); setCategory(null); }}
              >
                전체
              </button>
              {MAP_CATEGORIES.map((c) => (
                <button
                  key={c}
                  className={`chip${category === c ? " active" : ""}`}
                  onClick={() => { track("map_category", { category: c }); setCategory(category === c ? null : c); }}
                >
                  {c}
                </button>
              ))}
            </div>
          </div>
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
        <div className="filter-group">
          <label className="nearby-toggle">
            <input
              type="checkbox"
              checked={showNearby}
              onChange={(e) => { track("map_nearby", { on: e.target.checked }); setShowNearby(e.target.checked); }}
            />
            영양정보 없는 주변 식당도 보기
          </label>
        </div>
        {(sdkError ?? status) && <span className="map-status">{sdkError ?? status}</span>}
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
            골드 = 추천 상위 3곳
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
                {(() => {
                  const pick = reco.get(store.restaurant_id);
                  const name = pick?.menu_name ?? store.reco_menu;
                  if (!name) return null;
                  return (
                    <div className="store-reco">
                      <b>{name}</b>
                      <span>{pick?.reason ?? store.reco_reason}</span>
                    </div>
                  );
                })()}
              </div>
            );
          })}
          {showNearby && (
            <>
              <div className="store-list-divider">
                영양정보 없는 주변 식당 {nearby.length}곳 <span>카카오맵 · 등급 없음</span>
              </div>
              {nearby.map((place) => (
                <div
                  key={place.id}
                  className="store-card store-card-plain"
                  onClick={() => {
                    map.panTo(new window.kakao.maps.LatLng(Number(place.y), Number(place.x)));
                    showNearbyPopup(place);
                  }}
                >
                  <div className="store-card-head">
                    <span className="grade-badge grade-none" title="영양정보 없음">-</span>
                    <span className="store-card-name">{place.place_name}</span>
                    <span className="store-card-distance">{formatDistance(Number(place.distance))}</span>
                  </div>
                  <div className="store-card-address">{place.category_name}</div>
                </div>
              ))}
            </>
          )}
        </div>
      </div>
    </section>
  );
}
