// Step 3: 신체정보는 새 화면이 아니라 '한 끼 상한' 입력의 기본값 계산기다.
// Mifflin-St Jeor 로 하루 필요 kcal -> 3끼로 나눈 값. 참고용 근사치이며
// 의학적 조언이 아니다 (RecommendView 하단 문구 참고).

export const ACTIVITY_FACTORS = {
  sedentary: { label: "거의 안 움직임", factor: 1.2 },
  light: { label: "가벼운 활동", factor: 1.375 },
  moderate: { label: "보통 활동", factor: 1.55 },
  active: { label: "활발한 활동", factor: 1.725 },
};

// 질병관리청 국민건강영양조사 성인 평균 근사치. 신체정보를 입력하지 않은 사용자의
// 기본값이자, 신메뉴 표에서 "표준 남/여 기준"으로 쓰는 값.
export const KOREAN_AVG = {
  male: { heightCm: 173, weightKg: 74, age: 35 },
  female: { heightCm: 160, weightKg: 59, age: 35 },
};
export const DEFAULT_PROFILE = { ...KOREAN_AVG.male, sex: "male", activity: "light" };
export const profileFor = (sex) => ({ ...KOREAN_AVG[sex], sex, activity: "light" });

// 한 끼 단백질 권장량: KDRIs 성인 권장섭취량 0.91g/kg/일을 3끼로 나눈 근사치.
export function perMealProtein({ weightKg }) {
  const w = Number(weightKg);
  return w ? Math.round((w * 0.91) / 3) : null;
}

export function perMealCalorie({ heightCm, weightKg, age, sex, activity }) {
  const h = Number(heightCm), w = Number(weightKg), a = Number(age);
  if (!h || !w || !a) return null;
  const bmr = 10 * w + 6.25 * h - 5 * a + (sex === "female" ? -161 : 5);
  const factor = ACTIVITY_FACTORS[activity]?.factor ?? ACTIVITY_FACTORS.sedentary.factor;
  return Math.round((bmr * factor) / 3);
}

if (typeof process !== "undefined" && process.argv[1]?.endsWith("bmr.js")) {
  const male = perMealCalorie({ heightCm: 175, weightKg: 70, age: 30, sex: "male", activity: "sedentary" });
  console.assert(male === Math.round((10 * 70 + 6.25 * 175 - 5 * 30 + 5) * 1.2 / 3), "male BMR mismatch");
  console.assert(perMealCalorie({ heightCm: "", weightKg: 70, age: 30 }) === null, "missing field -> null");
  console.log("ok", male);
}
