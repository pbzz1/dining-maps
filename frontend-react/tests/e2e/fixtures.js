// E2E용 가짜 API 응답. 백엔드·DB 없이 프론트만 검증한다 (CI에서도 그대로 돈다).
// 형태는 app/*/schemas.py 의 Pydantic 모델을 따른다 -- 필드가 바뀌면 여기도 같이.

export const restaurants = [
  { id: 1, name: "샐러디", absolute_grade: "A", relative_grade: "A", good_menu_ratio: 0.9 },
  { id: 2, name: "맥도날드", absolute_grade: "C", relative_grade: "B", good_menu_ratio: 0.3 },
  // 등급 없는 브랜드 -- "정보 부족" 카드 분기를 태운다 (이 분기만 따로 깨진 적이 있다)
  { id: 3, name: "맘스터치", absolute_grade: null, relative_grade: null, good_menu_ratio: null },
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

// 목표·음식 종류별 브랜드 추천 메뉴 (/api/stores/brand-reco).
// "버거"를 고르면 샐러디는 후보에서 빠진다 -- 카테고리가 추천 목록 자체를 바꾸는 흐름.
export const brandReco = {
  diet: [
    { restaurant_id: 1, menu_item_id: 11, menu_name: "치킨 샐러드", category_group: "샐러드·샌드위치",
      reason: "320kcal · 다이어트 점수 80/100", score: 80, rank: 1 },
  ],
  protein: [
    { restaurant_id: 1, menu_item_id: 12, menu_name: "연어 샐러드", category_group: "샐러드·샌드위치",
      reason: "단백질 30g / 380kcal", score: 7.9, rank: 1 },
  ],
  버거: [],
};

export const authStatusOff = { enabled: false, provider: "kakao" };
export const authStatusOn = { enabled: true, provider: "kakao" };
export const me = { id: 1, provider: "kakao", nickname: "테스트유저", created_at: "2026-01-01T00:00:00Z", plan: "free" };
export const mePremium = { ...me, plan: "premium" };
// /api/memory (app/memory/schemas.py MemoryOut)
export const memoryList = [
  { id: 1, fact: "매운 양념 메뉴는 자주 뺀다", source: "ai", created_at: "2026-01-02T00:00:00Z" },
  { id: 2, fact: "점심은 회사 근처에서 먹는다", source: "user", created_at: "2026-01-03T00:00:00Z" },
];
// user_profile 은 가입 직후 전 필드 null 이다 -- 이 경우 프론트가 localStorage 값을 한 번 올린다.
export const emptyProfile = {
  goal: null, sex: null, height_cm: null, weight_kg: null, age: null, activity: null,
  max_calorie: null, max_sodium: null, exclude_drinks: false, allergies: null, dislikes: null,
};

// /api/recommend/personal (app/recommend/schemas.py PersonalRecoOut). items 는 /menus 와 같은 모양.
const pick = (id, name, reason) => ({
  menu_item_id: id, name, category: "샐러드", restaurant_id: 1, restaurant_name: "샐러디",
  calorie: 320, protein: 28, sodium: 500, sugar: 4, saturated_fat: 2,
  goal_score: 80, reason, nearest_store: null,
});
export const personalReco = {
  source: "llm",
  goal: "diet",
  comment: "오늘은 단백질이 많고 나트륨이 낮은 쪽으로 골랐습니다.",
  memory_added: [],
  impression_id: 501,
  variant: "ml",
  items: [
    pick(11, "치킨 샐러드", "단백질 28g에 320kcal라 한 끼 상한 안에서 포만감이 큽니다."),
    pick(12, "연어 샐러드", "나트륨 500mg으로 오늘 목표에 맞습니다."),
    pick(13, "두부 포케볼", "포화지방 2g으로 가볍습니다."),
  ],
};

// /api/chat (app/chat/schemas.py ChatOut). filters 는 서버가 누적해 돌려주는 조건.
export const chatFilters = (over = {}) => ({
  goal: null, max_calorie: null, max_sodium: null, exclude_drinks: null,
  include_groups: [], exclude_groups: [], include_brands: [], exclude_brands: [], include_words: [], spicy: null,
  ...over,
});
export const chatReply = (over = {}) => ({
  reply: "치킨 · 700kcal 이하 조건으로 골랐어요.",
  source: "filter",
  understood: true,
  filters: chatFilters({ include_groups: ["치킨"], max_calorie: 700 }),
  chips: [{ key: "group:치킨", label: "치킨" }, { key: "kcal", label: "700kcal 이하" }],
  items: personalReco.items,
  memory_added: [],
  limit_reached: false,
  ...over,
});

// /api/new-menus (app/new_menu/schemas.py NewMenuOut). 신메뉴 탭이 기본 화면이라
// 대부분의 스펙이 "/"로 들어가는 순간 이 호출이 나간다. base_name이 같은 두 행으로
// 옵션 묶기 분기(단품/라지)도 같이 태운다.
const newMenuItem = (id, name, base_name, overrides = {}) => ({
  id,
  name,
  base_name,
  restaurant_id: 1,
  restaurant_name: "샐러디",
  category_group: "샐러드",
  event_date: "2026-01-05",
  released_at: "2026-01-05",
  released_at_source: "press",
  first_seen_at: "2026-01-03",
  calorie: 320,
  protein: 28,
  sugar: 4,
  saturated_fat: 2,
  sodium: 500,
  weight_g: 300,
  nutrition_basis: "per_total",
  total_weight_g: null,
  scaled_to_total: false,
  diet_score: 80,
  absolute_grade: "A",
  image_url: null,
  youtube_video_id: null,
  calorie_brand_pct: 50,
  protein_brand_pct: 80,
  diet_verdict: null,
  diet_comment: null,
  taste_note: null,
  ...overrides,
});
export const newMenus = [
  newMenuItem(21, "두부 포케볼", "두부 포케볼"),
  newMenuItem(22, "두부 포케볼 (라지)", "두부 포케볼", { calorie: 420, protein: 34, sodium: 620 }),
];

// /api/recommend/menus (app/recommend/schemas.py RecommendedMenuOut 목록)
export const recommendMenus = [
  { menu_item_id: 31, name: "닭가슴살 샐러드", category: "샐러드", restaurant_id: 1, restaurant_name: "샐러디", calorie: 300, protein: 30, sodium: 480, sugar: 3, saturated_fat: 1, goal_score: 85, reason: "단백질 30g에 300kcal라 포만감이 큽니다.", nearest_store: null },
  { menu_item_id: 32, name: "두부 샐러드", category: "샐러드", restaurant_id: 1, restaurant_name: "샐러디", calorie: 280, protein: 22, sodium: 420, sugar: 2, saturated_fat: 1, goal_score: 78, reason: "나트륨 420mg으로 낮습니다.", nearest_store: null },
];

// /api/recommend/goals (app/recommend/schemas.py GoalOut, app/recommend/goals.py GOALS)
export const goals = [
  { key: "diet", label: "다이어트" },
  { key: "protein", label: "근성장" },
  { key: "low_sodium", label: "저나트륨" },
];

// 모든 스펙이 쓰는 기본 mock. 개별 테스트는 이 위에 page.route를 다시 걸어 덮어쓴다
// (Playwright는 나중에 등록한 route가 먼저 매칭된다).
export async function mockApi(page) {
  await page.route("**/api/stats/quality", (r) => r.fulfill({ json: [] }));
  // 기본은 비로그인 + 서버에 로그인이 꺼진 상태 -- 기존 스펙들이 보던 화면 그대로다.
  // 로그인 화면을 태우려면 스펙에서 이 위에 route를 다시 걸어 enabled:true로 덮는다.
  await page.route("**/api/auth/status", (r) => r.fulfill({ json: authStatusOff }));
  await page.route("**/api/auth/me", (r) => r.fulfill({ status: 401, json: { detail: "로그인이 필요합니다." } }));
  // 로그인한 스펙이 맞춤 추천 탭을 열면 이 호출이 나간다 -- 실제 백엔드로 새지 않게 기본값을 둔다.
  await page.route("**/api/recommend/personal*", (r) => r.fulfill({ json: personalReco }));
  // 신메뉴가 기본 화면이라 "/"로 들어가는 모든 스펙이 이 두 호출을 쏜다.
  await page.route("**/api/new-menus*", (r) => r.fulfill({ json: newMenus }));
  await page.route("**/api/recommend/menus*", (r) => r.fulfill({ json: recommendMenus }));
  await page.route("**/api/recommend/goals", (r) => r.fulfill({ json: goals }));
  await page.route("**/api/memory", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/chat", (r) => r.fulfill({ json: chatReply() }));
  await page.route("**/api/restaurants", (r) => r.fulfill({ json: restaurants }));
  await page.route("**/api/restaurants/1/stats", (r) => r.fulfill({ json: stats }));
  await page.route("**/api/restaurants/1/menu", (r) => r.fulfill({ json: menu }));
  await page.route("**/api/restaurants/1/diet-grade", (r) => r.fulfill({ json: dietGrade }));
  await page.route("**/api/stores?*", (r) => r.fulfill({ json: stores }));
  await page.route("**/api/stores/brand-reco*", (r) => {
    const q = new URL(r.request().url()).searchParams;
    const key = q.get("category") ?? q.get("goal") ?? "diet";
    r.fulfill({ json: brandReco[key] ?? [] });
  });
}
