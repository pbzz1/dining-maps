// 추천 카드 두 종류(목표 점수 목록, "오늘 당신에겐")가 같은 모양으로 수치를 보여 주도록
// 한 곳에 둔다. 한쪽만 고치면 같은 메뉴가 두 칸에서 다른 숫자로 보인다.

const NUTRIENTS = [
  ["열량", "calorie", "kcal"],
  ["단백질", "protein", "g"],
  ["당류", "sugar", "g"],
  ["포화지방", "saturated_fat", "g"],
  ["나트륨", "sodium", "mg"],
];

export function nutritionLine(m) {
  return NUTRIENTS.map(([label, key, unit]) => `${label} ${m[key] == null ? "-" : Math.round(m[key]) + unit}`).join(" · ");
}

export function storeMapUrl(m) {
  const s = m.nearest_store;
  return `https://map.kakao.com/link/map/${encodeURIComponent(s.branch_name ?? m.restaurant_name)},${s.lat},${s.lng}`;
}
