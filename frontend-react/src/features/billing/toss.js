// 토스페이먼츠 결제창(SDK v2). 요금제 페이지에서 결제 버튼을 누를 때만 스크립트를 내려받는다 --
// 다른 화면은 결제와 무관하니 첫 로딩에 실어 보내지 않는다.
// E2E 는 window.TossPayments 를 가짜로 심어 두고 이 파일을 그대로 태운다(스크립트 로딩은 건너뛴다).
const SDK_URL = "https://js.tosspayments.com/v2/standard";
export const CLIENT_KEY = import.meta.env.VITE_TOSS_CLIENT_KEY ?? "";

let loading = null;
export function loadTossSdk() {
  if (window.TossPayments) return Promise.resolve(window.TossPayments);
  if (!loading) {
    loading = new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = SDK_URL;
      s.onload = () => (window.TossPayments ? resolve(window.TossPayments) : reject(new Error("TossPayments 없음")));
      s.onerror = () => reject(new Error("결제 모듈을 불러오지 못했습니다."));
      document.head.appendChild(s);
    }).catch((e) => {
      loading = null; // 다음 클릭에 다시 시도
      throw e;
    });
  }
  return loading;
}

// 성공·실패 주소. 토스가 뒤에 ?paymentKey=…&orderId=…&amount=… (실패는 code/message/orderId) 를 붙여 돌려보낸다.
// 해시 라우팅이라 주소에 해시를 넣지 않고 쿼리 pay= 로 구분한다 -- App 이 읽어서 요금제 화면으로 보낸다.
const returnUrl = (kind) => `${location.origin}${location.pathname}?pay=${kind}`;

// order: /api/billing/checkout 응답. clientKey: 서버(/api/billing/me)가 준 키, 없으면 빌드 변수.
// 결제창은 페이지를 떠났다가 돌아오므로 이 함수는 보통 resolve 하지 않는다.
export async function requestCardPayment(order, clientKey = CLIENT_KEY) {
  const TossPayments = await loadTossSdk();
  const payment = TossPayments(clientKey).payment({ customerKey: order.customer_key });
  await payment.requestPayment({
    method: "CARD",
    amount: { currency: "KRW", value: order.amount },
    orderId: order.order_id,
    orderName: order.order_name,
    successUrl: returnUrl("success"),
    failUrl: returnUrl("fail"),
    card: { useEscrow: false, flowMode: "DEFAULT", useCardPoint: false, useAppCardOnly: false },
  });
}

// 토스에서 돌아온 주소를 읽고 지운다. 결제와 무관한 진입이면 null.
// 주소에 paymentKey 가 남아 있으면 새로고침마다 승인 요청이 다시 나가므로 읽는 즉시 지운다.
export function takePayReturnFromUrl() {
  const params = new URLSearchParams(location.search);
  const pay = params.get("pay");
  if (!pay) return null;
  const result =
    pay === "success"
      ? { status: "success", payment_key: params.get("paymentKey"), order_id: params.get("orderId"), amount: Number(params.get("amount")) }
      : { status: "fail", code: params.get("code"), message: params.get("message"), order_id: params.get("orderId") };
  for (const k of ["pay", "paymentKey", "orderId", "amount", "code", "message"]) params.delete(k);
  const qs = params.toString();
  history.replaceState(null, "", `${location.pathname}${qs ? `?${qs}` : ""}#plans`);
  return result;
}
