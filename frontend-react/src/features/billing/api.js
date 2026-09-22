import { get, post } from "../../api";

// 요금제 표(공개). 가격·모델은 서버 설정이 정본이라 화면에 숫자를 박아 두지 않는다.
export const fetchPlans = () => get("/billing/plans");
// 지금 요금제·만료일·남은 AI 예산·결제 가능 여부. 결제 직후 바뀌므로 캐시하지 않는다.
export const fetchBillingMe = () => get("/billing/me", undefined, { fresh: true });
// 주문번호·금액 발급. 금액은 여기서 받은 값을 그대로 토스에 넘긴다(서버가 승인 때 대조한다).
export const checkout = (plan) => post("/billing/checkout", { plan });
// 토스 성공 리다이렉트의 paymentKey/orderId/amount 를 서버에 넘겨 승인시킨다. 이용권은 여기서 생긴다.
export const confirmPayment = (body) => post("/billing/confirm", body);
