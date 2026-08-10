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
