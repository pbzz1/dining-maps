import { del, get, post, put } from "../../api";

// 서버에 카카오 키가 없으면 enabled:false -- 로그인 버튼 자체를 숨긴다.
export const fetchAuthStatus = () => get("/auth/status");
// 둘 다 fresh -- 결제·동의 뒤 refresh() 가 캐시된 옛 응답(요금제·동의 상태)을 받으면 화면이 안 바뀐다.
export const fetchMe = () => get("/auth/me", undefined, { fresh: true });
export const fetchProfile = () => get("/profile", undefined, { fresh: true });
export const saveProfile = (profile) => put("/profile", profile);
export const deleteAccount = () => del("/me");
// 신체정보(성별·키·몸무게·나이·알레르기) 계정 저장 동의. 철회하면 서버가 저장된 값을 바로 지운다.
export const grantHealthConsent = () => post("/auth/consent/health");
export const withdrawHealthConsent = () => del("/auth/consent/health");

// 추천 카드를 눌렀다/숨겼다. 실패해도 화면은 그대로 가야 하므로 여기서 삼킨다 --
// 개인화 신호 하나 놓치는 것과 사용자 동작이 막히는 것은 비교 대상이 아니다.
// ctx: { impression_id, surface, position } -- 어느 노출의 몇 번째 카드였는지. 학습형 추천이
// "보여준 것 중 이걸 골랐다"를 배우는 연결고리라, 추천 카드에서 부를 땐 꼭 넘긴다.
export const logEvent = (event_type, menu_item_id = null, ctx = {}) =>
  post("/events", { event_type, menu_item_id, ...ctx }).catch(() => {});

// 로그인은 fetch가 아니라 페이지 이동이다 -- 카카오 동의화면을 거쳐야 해서
// XHR로는 끝까지 갈 수 없다. 돌아올 때 API가 ?token=... 을 붙여 프론트로 보낸다.
export function startLogin() {
  const base = import.meta.env.VITE_API_BASE ?? "";
  location.href = `${base}/api/auth/kakao/login`;
}
