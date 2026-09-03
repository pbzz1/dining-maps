// All API calls go through here so the base URL is configured in one place.
// Dev: empty base -> "/api/..." hits the Vite proxy (see vite.config.js).
// Prod: set VITE_API_BASE to the deployed FastAPI origin at build time.
const BASE = import.meta.env.VITE_API_BASE ?? "";

// URL -> Promise. 진행 중인 요청 dedupe와 이미 받아온 응답 재사용이 같은 한 줄로 해결된다.
// ponytail: TTL 없음 (SPA 세션 = 캐시 수명). 크롤이 하루 1회라 새로고침이면 충분.
// 장수 세션에서 신선도가 문제되면 { at, promise }로 바꾸고 TTL 비교를 넣는다.
const cache = new Map();

export function get(path, params) {
  const url = `${BASE}/api${path}${params ? `?${new URLSearchParams(params)}` : ""}`;
  let p = cache.get(url);
  if (!p) {
    p = fetch(url).then((res) => {
      if (!res.ok) throw new Error(`${path} -> HTTP ${res.status}`);
      return res.json();
    });
    p.catch(() => cache.delete(url)); // 실패는 캐시하지 않는다 -- 재시도가 살아 있어야
    cache.set(url, p);
  }
  return p;
}

export const fetchRestaurants = () => get("/restaurants");
export const fetchDietGrade = (id) => get(`/restaurants/${id}/diet-grade`);
export const fetchStats = (id) => get(`/restaurants/${id}/stats`);
export const fetchMenu = (id) => get(`/restaurants/${id}/menu`);
export const fetchStores = (params) => get("/stores", params);
export const fetchStatsBrands = () => get("/stats/brands");
export const fetchStatsQuality = () => get("/stats/quality");
// 메뉴 탐색기. params: { sort, category?, restaurant_id?, limit? }
export const fetchMenus = (params) => get("/menus", params);
// 신메뉴 피드: 최근 크롤에서 새로 발견된 메뉴 + LLM 리뷰
// params: { days?, per_brand?, limit? } -- "이전 신메뉴 더 보기"가 창을 넓힐 때
export const fetchNewMenus = (params) => get("/new-menus", params);
