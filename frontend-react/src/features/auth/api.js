import { del, get, post, put } from "../../api";

// 서버에 카카오 키가 없으면 enabled:false -- 로그인 버튼 자체를 숨긴다.
export const fetchAuthStatus = () => get("/auth/status");
export const fetchMe = () => get("/auth/me");
export const fetchProfile = () => get("/profile");
export const saveProfile = (profile) => put("/profile", profile);
export const deleteAccount = () => del("/me");

// 추천 카드를 눌렀다/숨겼다. 실패해도 화면은 그대로 가야 하므로 여기서 삼킨다 --
// 개인화 신호 하나 놓치는 것과 사용자 동작이 막히는 것은 비교 대상이 아니다.
export const logEvent = (event_type, menu_item_id = null) =>
  post("/events", { event_type, menu_item_id }).catch(() => {});

// 로그인은 fetch가 아니라 페이지 이동이다 -- 카카오 동의화면을 거쳐야 해서
// XHR로는 끝까지 갈 수 없다. 돌아올 때 API가 ?token=... 을 붙여 프론트로 보낸다.
export function startLogin() {
  const base = import.meta.env.VITE_API_BASE ?? "";
  location.href = `${base}/api/auth/kakao/login`;
}
