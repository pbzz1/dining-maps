export const NUTRIENT_LABELS = {
  calorie: "칼로리",
  protein: "단백질",
  carb: "탄수화물",
  fat: "지방",
  sugar: "당류",
  saturated_fat: "포화지방",
  sodium: "나트륨",
  caffeine: "카페인",
};

export const GRADE_CLASS = { A: "grade-a", B: "grade-b", C: "grade-c", D: "grade-d" };
export const GRADE_COLOR = { A: "#2f8f4e", B: "#6fa83d", C: "#d99a2b", D: "#c1440e" };
export const GRADE_RANK = { A: 0, B: 1, C: 2, D: 3 };
export const ALL_GRADES = ["A", "B", "C", "D"];

// Short sub-label under each tier's grade letter -- what the letter actually
// means differs by mode (a rank slice vs. a fixed score band), so the caption
// has to switch with the toggle too, not just the grade itself.
export const TIER_CAPTION = {
  relative: { A: "상위 25%", B: "26~50%", C: "51~75%", D: "하위 25%" },
  absolute: { A: "80점 이상", B: "60~79점", C: "40~59점", D: "40점 미만" },
};

// Faint tint/border for a tier-list card -- alpha appended as hex, GRADE_COLOR
// entries are always 6-digit hex so this is safe.
export function gradeTint(grade) {
  return grade ? `${GRADE_COLOR[grade]}17` : undefined;
}
export function gradeBorder(grade) {
  return grade ? `${GRADE_COLOR[grade]}55` : undefined;
}

// Plain-language recommendation for a menu item, from its *absolute* (WHO/
// 논문 fixed) grade -- relative grade shifts as the catalog changes, so it's
// the wrong basis for "should I eat this". A/B -> 추천 (already the "다이어트
// 메뉴" cutoff used for good_menu_ratio elsewhere), C -> 보통, D -> 비추천.
export function recommendLabel(absoluteGrade) {
  if (absoluteGrade === "A" || absoluteGrade === "B") return "추천";
  if (absoluteGrade === "C") return "보통";
  if (absoluteGrade === "D") return "비추천";
  return null;
}
export const RECOMMEND_COLOR = { 추천: GRADE_COLOR.A, 보통: GRADE_COLOR.C, 비추천: GRADE_COLOR.D };

// Matches each brand's CSV basename under data/ (same slug load_data.py uses),
// so a real logo just has to land at /logos/<slug>.png -- no code change needed.
export const BRAND_SLUGS = {
  버거킹: "burgerking",
  빽다방: "paikdabang",
  샐러디: "salady",
  이디야: "ediya",
  커피빈: "coffeebean",
  할리스: "hollys",
  교촌치킨: "kyochon",
  롯데리아: "lotteria",
  맘스터치: "momstouch",
  맥도날드: "mcdonalds",
  서브웨이: "subway",
  스타벅스: "starbucks",
  도미노피자: "dominos",
  포케올데이: "pokeallday",
  배스킨라빈스: "baskinrobbins",
  BHC: "bhc",
};

export const DEFAULT_CENTER = { lat: 37.5665, lng: 126.978 }; // 서울시청
export const SEARCH_RADIUS_M = 3000;

export const SORT_OPTIONS = [
  { value: "name", label: "이름순" },
  { value: "calorie_asc", label: "칼로리 낮은순" },
  { value: "calorie_desc", label: "칼로리 높은순" },
  { value: "protein_desc", label: "단백질 높은순" },
  { value: "grade_absolute", label: "등급 좋은순 (절대)" },
  { value: "grade_relative", label: "등급 좋은순 (상대)" },
];

export function formatValue(value, unit) {
  const rounded = Number.isInteger(value) ? value : Math.round(value * 10) / 10;
  return `${rounded}${unit}`;
}

export function formatDistance(m) {
  if (m == null) return "";
  return m < 1000 ? `${Math.round(m)}m` : `${(m / 1000).toFixed(1)}km`;
}
