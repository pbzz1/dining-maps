// E2E용 가짜 API 응답. 백엔드·DB 없이 프론트만 검증한다 (CI에서도 그대로 돈다).
// 형태는 app/*/schemas.py 의 Pydantic 모델을 따른다 -- 필드가 바뀌면 여기도 같이.

export const restaurants = [
  { id: 1, name: "샐러디", absolute_grade: "A", relative_grade: "A", good_menu_ratio: 0.9 },
  { id: 2, name: "맥도날드", absolute_grade: "C", relative_grade: "B", good_menu_ratio: 0.3 },
];

export const stats = {
  restaurant_id: 1,
  restaurant_name: "샐러디",
  menu_item_count: 2,
  averages: [{ nutrient_name: "calorie", unit: "kcal", avg_value: 350, item_count: 2 }],
};

export const dietGrade = {
  restaurant_id: 1,
  restaurant_name: "샐러디",
  scored_item_count: 2,
  avg_score: 80,
  absolute_grade: "A",
  relative_grade: "A",
  good_menu_count: 2,
  good_menu_ratio: 1,
};

const item = (id, name, kcal) => ({
  id,
  name,
  category: "샐러드",
  price_krw: 8900,
  weight_g: 300,
  allergy_info: null,
  origin_info: null,
  data_source: null,
  nutrition: [{ nutrient_name: "calorie", value: kcal, unit: "kcal" }],
  diet_score: 80,
  absolute_grade: "A",
  relative_grade: "A",
  percentile: 90,
});
export const menu = [item(11, "치킨 샐러드", 320), item(12, "연어 샐러드", 380)];

export const stores = [
  {
    id: 100,
    restaurant_id: 1,
    restaurant_name: "샐러디",
    branch_name: "시청점",
    address: "서울 중구",
    lat: 37.5665,
    lng: 126.978,
    distance_m: 120,
    avg_score: 80,
    absolute_grade: "A",
    relative_grade: "A",
    good_menu_ratio: 0.9,
  },
];

// 모든 스펙이 쓰는 기본 mock. 개별 테스트는 이 위에 page.route를 다시 걸어 덮어쓴다
// (Playwright는 나중에 등록한 route가 먼저 매칭된다).
export async function mockApi(page) {
  await page.route("**/api/stats/quality", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/restaurants", (r) => r.fulfill({ json: restaurants }));
  await page.route("**/api/restaurants/1/stats", (r) => r.fulfill({ json: stats }));
  await page.route("**/api/restaurants/1/menu", (r) => r.fulfill({ json: menu }));
  await page.route("**/api/restaurants/1/diet-grade", (r) => r.fulfill({ json: dietGrade }));
  await page.route("**/api/stores?*", (r) => r.fulfill({ json: stores }));
}
