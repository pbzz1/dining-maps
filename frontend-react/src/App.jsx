import { useEffect, useRef, useState } from "react";
import MapView from "./features/map/MapView";
import RestaurantList from "./features/restaurants/RestaurantList";
import MenuView from "./features/restaurants/MenuView";
import Dashboard from "./features/dashboard/Dashboard";
import RecommendView from "./features/recommend/RecommendView";
import NewMenuView from "./features/new-menu/NewMenuView";
import AboutView from "./features/about/AboutView";
import PlansView from "./features/billing/PlansView";
import ProfileView from "./features/profile/ProfileView";
import { takePayReturnFromUrl } from "./features/billing/toss";
import LoginButton from "./features/auth/LoginButton";
import ChatFab from "./features/chat/ChatFab";
import { useAuth } from "./features/auth/useAuth";
import { fetchStatsQuality } from "./api";
import { track } from "./constants";
import LogoMark from "./components/Logo";
import { IconDashboard, IconStar, IconPin, IconList, IconSparkle } from "./components/NavIcons";
import "./App.css";

const NAV = [
  { key: "new", label: "신메뉴", Icon: IconSparkle },
  { key: "recommend", label: "맞춤 추천", Icon: IconStar },
  { key: "map", label: "지도", Icon: IconPin },
  { key: "dashboard", label: "대시보드", Icon: IconDashboard },
  { key: "list", label: "매장 목록", Icon: IconList },
];

// about·plans·me 는 NAV에 없다 -- 사이드바엔 안 뜨지만 #about / #plans / #me 링크로는 열린다.
// me(내 정보)는 상단바의 닉네임 단추가 입구다.
const VIEWS = new Set([...NAV.map((n) => n.key), "about", "plans", "me"]);
// URL 해시가 곧 현재 뷰 -- "#list" 같은 링크를 공유하면 그 탭으로 바로 열린다.
// 기본 화면은 신메뉴: 입력·로그인·위치 없이 바로 볼 게 있고 주 2회 내용이 바뀐다.
// 지도는 "#map"으로 그대로 열린다 (공유된 링크 유지).
const HOME_VIEW = "new";
const viewFromHash = () => (VIEWS.has(location.hash.slice(1)) ? location.hash.slice(1) : HOME_VIEW);

// 뷰별 문서 제목. SPA라 제목이 처음 것 그대로면 브라우저 탭·방문기록·북마크가 전부
// 같은 이름이 되고, GA4 "페이지 제목 및 화면 클래스" 보고서에서도 모든 뷰가 한 줄로 뭉친다.
const VIEW_LABEL = { ...Object.fromEntries(NAV.map((n) => [n.key, n.label])), menu: "메뉴", about: "소개", plans: "요금제", me: "내 정보" };
const HOME_TITLE = "Dining Maps - 프랜차이즈 신메뉴 영양 분석과 내 기준 메뉴 추천"; // index.html과 같은 문구
const titleFor = (v) => (v === HOME_VIEW ? HOME_TITLE : `Dining Maps - ${VIEW_LABEL[v] ?? v}`);

// SPA 뷰 전환을 GA4에 page_view로 보낸다. gtag('config')는 첫 로딩 때 한 번만 발생하고,
// setView는 history.pushState로 해시만 바꾸므로 그 뒤의 이동은 아무 데도 안 잡혔다.
// 2026-09 보고서에서 조회수가 사실상 첫 화면 한 줄에 몰려 있던 게 이것 때문이다.
//
// 주의: GA4 향상된 측정의 "브라우저 기록 이벤트 기반 변경"이 켜져 있으면 pushState마다
// GA가 자체 page_view를 또 쏴서 두 번 집계된다 -- 속성 설정에서 그 항목을 꺼야 한다.
function usePageViewTracking(view) {
  const first = useRef(true);
  useEffect(() => {
    document.title = titleFor(view);
    if (first.current) {
      first.current = false; // 최초 조회는 gtag('config')가 이미 보냈다
      return;
    }
    track("page_view", { page_title: document.title, page_location: location.href });
  }, [view]);
}

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
  // 토스 결제창에서 돌아온 진입(?pay=success|fail)인지 먼저 본다 -- 주소를 #plans 로 바꾸므로
  // 아래 viewFromHash 보다 앞서 돌아야 한다(useState 초기화는 선언 순서대로 실행된다).
  const [payReturn] = useState(takePayReturnFromUrl);
  const [view, setViewRaw] = useState(viewFromHash); // map | list | menu | dashboard | recommend | about | plans | me
  const [selected, setSelected] = useState(null);
  const [dataDate, setDataDate] = useState("");
  // 로그인 상태는 여기 한 곳에서만 만든다 -- 상단바 버튼과 맞춤 추천이 같은 값을 본다.
  const auth = useAuth();
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
  usePageViewTracking(view);

  // 모바일에서 내비는 가로 스크롤 줄이라 현재 탭이 화면 밖일 수 있다 -- 잘려 있으면 끌어온다.
  useEffect(() => {
    document.querySelector(".nav-btn.active")?.scrollIntoView({ inline: "nearest", block: "nearest" });
  }, [activeNav]);

  return (
    <div className="shell">
      <header className="topbar">
        {/* 로고 = 홈. 해시를 지우고 새로고침해서 첫 화면(신메뉴)으로 완전히 초기화한다. */}
        <h1 className="brand">
          <a href="/">
            <LogoMark size={34} />
            <span className="wordmark">Dining Maps</span>
          </a>
        </h1>
        <span className="subtitle">
          신메뉴 영양 분석, 내 기준에 맞는 메뉴 추천
          {" · "}
          {/* 기준일을 아직 못 받아왔어도 링크는 남긴다 -- 데스크톱의 유일한 #about 진입점. */}
          <a href="#about" onClick={() => track("view_change", { view: "about" })}>
            브랜드 공식 영양정보{dataDate && ` ${dataDate}`} 기준
          </a>
        </span>
        <LoginButton auth={auth} />
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
        {/* Once opened, MapView stays mounted (just hidden) so the Kakao map instance
            and its markers survive tab switches -- rebuilding it each time is slow and
            would lose the current center. It is not mounted before the first visit:
            the map is no longer the home view, and mounting it loads the Kakao SDK
            and fetches /api/stores. */}
        {seen.has("map") && (
          <div className="map-wrap" style={{ display: view === "map" ? "flex" : "none" }}>
            <MapView onOpenMenu={openMenu} visible={view === "map"} />
          </div>
        )}
        <Pane name="dashboard" view={view} seen={seen}><Dashboard /></Pane>
        <Pane name="recommend" view={view} seen={seen}><RecommendView auth={auth} /></Pane>
        <Pane name="new" view={view} seen={seen}><NewMenuView /></Pane>
        <Pane name="about" view={view} seen={seen}><AboutView dataDate={dataDate} /></Pane>
        <Pane name="plans" view={view} seen={seen}><PlansView auth={auth} payReturn={payReturn} /></Pane>
        <Pane name="me" view={view} seen={seen}><ProfileView auth={auth} visible={view === "me"} /></Pane>
        <Pane name="list" view={view} seen={seen}><RestaurantList onSelect={openMenu} /></Pane>
        {/* 드릴다운은 매장마다 내용이 달라 keep-alive 대상이 아니다 -- api.js 캐시가 커버. */}
        {view === "menu" && selected && (
          <div className="view-wrap" style={{ display: "flex" }}>
            <MenuView restaurant={selected} onBack={() => setView("list")} />
          </div>
        )}
      </main>

      {/* 지도에선 숨긴다 -- 오른쪽 아래가 지도 조작·범례 자리다. 숨기기만 하니 대화는 남는다. */}
      <ChatFab auth={auth} hidden={view === "map"} />
    </div>
  );
}
