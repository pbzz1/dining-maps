// 요금제 판정 한 곳. 서버(/api/auth/me)가 지금 유효한 이용권으로 계산한 plan 을 준다:
//   free     -- 학습형 추천 + 조건 검색 대화. LLM 없음
//   standard -- Claude Haiku 4.5 로 AI 추천·AI 대화·AI 메모리
//   high     -- 같은 기능, Claude Sonnet 5
// 예전의 "premium" 문자열 비교는 전부 여기로 모았다 -- 요금제가 늘어도 화면 코드는 안 바뀐다.
export const PLAN_LABEL = { free: "Free", standard: "Standard", high: "High" };

export const isPaid = (user) => user?.plan === "standard" || user?.plan === "high";

// 화면에 보이는 "이번 기간 AI 남은 양" 문구. 막대·링 없이 글자로만 (DESIGN.md: 게이미피케이션 금지).
export const quotaLine = (pct) => (pct == null ? "" : `이번 기간 AI 남은 양 ${pct}%`);
