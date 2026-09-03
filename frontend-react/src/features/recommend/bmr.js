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

export function perMealCalorie({ heightCm, weightKg, age, sex, activity }) {
  const h = Number(heightCm), w = Number(weightKg), a = Number(age);
  if (!h || !w || !a) return null;
  const bmr = 10 * w + 6.25 * h - 5 * a + (sex === "female" ? -161 : 5);
  const factor = ACTIVITY_FACTORS[activity]?.factor ?? ACTIVITY_FACTORS.sedentary.factor;
  return Math.round((bmr * factor) / 3);
}

// 저장된 프로필이 반쯤 비어 있거나(입력하다 지움) 말이 안 되는 값이면(체중 7400)
// 그 칸만 같은 성별 한국 평균으로 메운다 -- 신메뉴 표가 빈 배지나 엉뚱한 판정을
// 내지 않게. 맞춤 추천 화면은 원본을 그대로 쓴다.
const RANGES = { heightCm: [120, 230], weightKg: [30, 250], age: [10, 100] };
export function sanitizeProfile(profile) {
  const sex = profile?.sex === "female" ? "female" : "male";
  const out = { sex, activity: ACTIVITY_FACTORS[profile?.activity] ? profile.activity : "light" };
  for (const [k, [lo, hi]] of Object.entries(RANGES)) {
    const v = Number(profile?.[k]);
    out[k] = v >= lo && v <= hi ? v : KOREAN_AVG[sex][k];
  }
  return out;
}

if (typeof process !== "undefined" && process.argv[1]?.endsWith("bmr.js")) {
  const male = perMealCalorie({ heightCm: 175, weightKg: 70, age: 30, sex: "male", activity: "sedentary" });
  console.assert(male === Math.round((10 * 70 + 6.25 * 175 - 5 * 30 + 5) * 1.2 / 3), "male BMR mismatch");
  console.assert(perMealCalorie({ heightCm: "", weightKg: 70, age: 30 }) === null, "missing field -> null");
  console.log("ok", male);
}
