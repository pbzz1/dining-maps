// All API calls go through here so the base URL is configured in one place.
// Dev: empty base -> "/api/..." hits the Vite proxy (see vite.config.js).
// Prod: set VITE_API_BASE to the deployed FastAPI origin at build time.
const BASE = import.meta.env.VITE_API_BASE ?? "";

// URL -> Promise. 진행 중인 요청 dedupe와 이미 받아온 응답 재사용이 같은 한 줄로 해결된다.
// ponytail: TTL 없음 (SPA 세션 = 캐시 수명). 크롤이 하루 1회라 새로고침이면 충분.
// 장수 세션에서 신선도가 문제되면 { at, promise }로 바꾸고 TTL 비교를 넣는다.
const cache = new Map();

// 로그인 토큰. 모듈 변수로 두는 이유: 매 요청마다 localStorage를 읽지 않기 위해서고,
// useAuth가 로그인/로그아웃 때 setToken으로 갈아끼운다. 여기 있는 값이 정본.
const TOKEN_KEY = "auth.token";
let token = (() => {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null; // 사파리 프라이빗 등 localStorage가 막힌 환경 -- 비로그인으로 동작
  }
})();

export const getToken = () => token;

export function setToken(next) {
  token = next;
  try {
    if (next) localStorage.setItem(TOKEN_KEY, next);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* 저장만 실패 -- 이번 세션 동안은 메모리의 token으로 계속 로그인 상태다 */
  }
  // 로그인/로그아웃 전후로 같은 URL이 다른 응답을 주므로 캐시를 통째로 버린다.
  cache.clear();
}

const authHeaders = () => (token ? { Authorization: `Bearer ${token}` } : {});

function toUrl(path, params) {
  return `${BASE}/api${path}${params ? `?${new URLSearchParams(params)}` : ""}`;
}

async function body(res, path) {
  if (!res.ok) {
    const err = new Error(`${path} -> HTTP ${res.status}`);
    err.status = res.status; // 401을 호출부가 "토큰 만료"로 구분할 수 있게
    throw err;
  }
  return res.status === 204 ? null : res.json();
}

export function get(path, params) {
  const url = toUrl(path, params);
  let p = cache.get(url);
  if (!p) {
    p = fetch(url, { headers: authHeaders() }).then((res) => body(res, path));
    p.catch(() => cache.delete(url)); // 실패는 캐시하지 않는다 -- 재시도가 살아 있어야
    cache.set(url, p);
  }
  return p;
}

// 쓰기는 캐시하지 않는다 -- 같은 호출을 두 번 하는 게 곧 의미인 경우(이벤트 기록)가 있다.
function send(method, path, payload) {
  return fetch(toUrl(path), {
    method,
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: payload === undefined ? undefined : JSON.stringify(payload),
  }).then((res) => body(res, path));
}

export const post = (path, payload) => send("POST", path, payload);
export const put = (path, payload) => send("PUT", path, payload);
export const del = (path) => send("DELETE", path);

export const fetchRestaurants = () => get("/restaurants");
export const fetchDietGrade = (id) => get(`/restaurants/${id}/diet-grade`);
export const fetchStats = (id) => get(`/restaurants/${id}/stats`);
export const fetchMenu = (id) => get(`/restaurants/${id}/menu`);
export const fetchStores = (params) => get("/stores", params);
// 지도 추천의 "무엇을 먹을지" 축. params: { goal, category? } -- 매장 목록과 따로 불러서
// 목표만 바꿀 때 반경 안 매장을 다시 받지 않는다.
export const fetchBrandReco = (params) => get("/stores/brand-reco", params);
export const fetchStatsBrands = () => get("/stats/brands");
export const fetchStatsQuality = () => get("/stats/quality");
// 메뉴 탐색기. params: { sort, category?, restaurant_id?, limit? }
export const fetchMenus = (params) => get("/menus", params);
// 신메뉴 피드: 최근 크롤에서 새로 발견된 메뉴 + LLM 리뷰
// params: { days?, per_brand?, limit? } -- "이전 신메뉴 더 보기"가 창을 넓힐 때
export const fetchNewMenus = (params) => get("/new-menus", params);
