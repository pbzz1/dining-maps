// All API calls go through here so the base URL is configured in one place.
// Dev: empty base -> "/api/..." hits the Vite proxy (see vite.config.js).
// Prod: set VITE_API_BASE to the deployed FastAPI origin at build time.
const BASE = import.meta.env.VITE_API_BASE ?? "";

async function get(path, params) {
  const qs = params ? `?${new URLSearchParams(params)}` : "";
  const res = await fetch(`${BASE}/api${path}${qs}`);
  if (!res.ok) throw new Error(`${path} -> HTTP ${res.status}`);
  return res.json();
}

export const fetchRestaurants = () => get("/restaurants");
export const fetchDietGrade = (id) => get(`/restaurants/${id}/diet-grade`);
export const fetchStats = (id) => get(`/restaurants/${id}/stats`);
export const fetchMenu = (id) => get(`/restaurants/${id}/menu`);
export const fetchStores = (params) => get("/stores", params);
export const fetchStatsBrands = () => get("/stats/brands");
export const fetchStatsQuality = () => get("/stats/quality");
