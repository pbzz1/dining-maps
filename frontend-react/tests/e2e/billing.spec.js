// 유료 요금제·결제. 지키는 것:
// (1) 요금제 페이지(#plans)는 서버 설정의 가격·모델을 표로 보여주고, 비로그인은 결제 대신 로그인 안내
// (2) 결제 흐름: 결제 버튼 -> checkout -> 토스 결제창(가짜) -> 성공 주소로 복귀 -> 서버 승인(금액은 서버가 준 값)
//     -> 완료 문구. 주소의 paymentKey 는 읽는 즉시 지운다
// (3) 실패 주소로 돌아오면 실패 문구
// (4) 결제 전·후 화면 차이: 무료는 "요금제" 링크, 유료는 "AI 추천"과 "이번 기간 AI 남은 양"
// (5) AI 예산을 다 쓰면 추천·대화 모두 "다 써서 무료 방식으로 답했다"고 알린다
// (6) 이용 중인 요금제는 "30일 연장", 다른 요금제는 비활성(업그레이드는 v1 에서 막는다)
import { expect, test } from "@playwright/test";
import {
  authStatusOn, billingPaid, chatReply, checkoutOrder, emptyProfile, entitlement, me, mePaid, mockApi, personalReco,
} from "./fixtures";

async function base(page, user = null) {
  await mockApi(page);
  await page.route("**/api/recommend/goals", (r) => r.fulfill({ json: [{ key: "diet", label: "다이어트" }] }));
  await page.route("**/api/recommend/menus?*", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/auth/status", (r) => r.fulfill({ json: authStatusOn }));
  await page.route("**/api/profile", (r) => r.fulfill({ json: emptyProfile }));
  if (user) await page.route("**/api/auth/me", (r) => r.fulfill({ json: user }));
}

// 진짜 토스 SDK 대신: requestPayment 를 부르면 성공 주소로 이동한다(토스가 하는 일과 같은 모양).
const fakeToss = (paymentKey = "pk_e2e") =>
  `window.TossPayments = (clientKey) => ({
    payment: ({ customerKey }) => ({
      requestPayment: async (p) => {
        // 성공 주소로 이동하면 window 가 새로 뜨므로 호출 기록은 sessionStorage 에 남긴다
        const calls = JSON.parse(sessionStorage.getItem("__tossCalls") ?? "[]");
        sessionStorage.setItem("__tossCalls", JSON.stringify([...calls, { clientKey, customerKey, p }]));
        location.href = p.successUrl + "&paymentKey=${paymentKey}&orderId=" + p.orderId + "&amount=" + p.amount.value;
      },
    }),
  });`;

test("요금제 페이지는 서버 가격·모델을 표로 보여주고, 비로그인은 로그인 안내다", async ({ page }) => {
  await base(page);
  await page.goto("/#plans");
  await expect(page.getByRole("heading", { name: "요금제" })).toBeVisible();
  const table = page.getByRole("table");
  await expect(table.getByRole("columnheader", { name: "Standard" })).toBeVisible();
  await expect(table.getByText("3,900원")).toBeVisible();
  await expect(table.getByText("9,900원")).toBeVisible();
  await expect(table.getByText("Claude Haiku 4.5")).toBeVisible();
  await expect(table.getByText("Claude Sonnet 5")).toBeVisible();
  await expect(table.getByRole("button", { name: "카카오로 로그인" })).toHaveCount(2);
  await expect(page.getByRole("button", { name: /시작$/ })).toHaveCount(0);
});

test("결제: 버튼 -> checkout -> 토스(가짜) -> 성공 복귀 -> 서버 승인 -> 완료 문구", async ({ page }) => {
  await base(page, me);
  const checkouts = [];
  await page.route("**/api/billing/checkout", (r) => {
    checkouts.push(r.request().postDataJSON());
    r.fulfill({ json: checkoutOrder });
  });
  const confirms = [];
  await page.route("**/api/billing/confirm", (r) => {
    confirms.push(r.request().postDataJSON());
    r.fulfill({ json: entitlement });
  });
  await page.addInitScript(fakeToss());

  await page.goto("/?token=fake-jwt#plans");
  await page.getByRole("button", { name: "Standard 시작" }).click();
  await expect.poll(() => checkouts).toEqual([{ plan: "standard" }]);

  // 토스가 하듯 성공 주소로 돌아온다. 앱은 주소의 결제 파라미터를 읽어 서버 승인을 부른다.
  await expect(page.getByRole("status")).toContainText("Standard 이용권이 시작됐어요");
  expect(confirms).toEqual([{ payment_key: "pk_e2e", order_id: checkoutOrder.order_id, amount: checkoutOrder.amount }]);
  // 결제창에 넘긴 값은 서버가 준 주문 그대로다(금액을 화면이 정하지 않는다)
  const calls = await page.evaluate(() => JSON.parse(sessionStorage.getItem("__tossCalls") ?? "[]"));
  expect(calls).toHaveLength(1);
  expect(calls[0].clientKey).toBe("test_ck_e2e");
  expect(calls[0].customerKey).toBe(checkoutOrder.customer_key);
  expect(calls[0].p.amount).toEqual({ currency: "KRW", value: 3900 });
  expect(calls[0].p.orderId).toBe(checkoutOrder.order_id);
  // paymentKey 가 주소에 남으면 새로고침마다 승인이 다시 나간다 -- 읽는 즉시 지운다
  await expect(page).toHaveURL(/#plans$/);
  expect(page.url()).not.toContain("paymentKey");
});

test("실패 주소로 돌아오면 실패 문구를 보여주고 승인은 부르지 않는다", async ({ page }) => {
  await base(page, me);
  let confirmed = false;
  await page.route("**/api/billing/confirm", (r) => {
    confirmed = true;
    r.fulfill({ json: entitlement });
  });
  await page.goto("/?token=fake-jwt&pay=fail&code=PAY_PROCESS_CANCELED&message=%EC%B7%A8%EC%86%8C&orderId=dm_x");
  await expect(page.getByRole("status")).toContainText("결제가 되지 않았어요");
  await expect(page.getByRole("heading", { name: "요금제" })).toBeVisible();
  expect(confirmed).toBe(false);
  expect(page.url()).not.toContain("pay=");
});

test("결제 전: 무료 추천에는 요금제 링크가, 결제 후: AI 추천과 남은 양이 보인다", async ({ page }) => {
  await base(page, me);
  await page.route("**/api/recommend/personal*", (r) =>
    r.fulfill({ json: { ...personalReco, source: "personal", comment: null, plan: "free", ai_budget_left_pct: null } })
  );
  await page.goto("/?token=fake-jwt#recommend");
  const s = page.getByRole("region", { name: "오늘 당신에겐" });
  await expect(s.getByText("내 설정·기록 기반")).toBeVisible();
  await expect(s.getByRole("link", { name: "AI가 고르는 추천은 요금제에서" })).toHaveAttribute("href", "#plans");
  await expect(s.getByText(/AI 남은 양/)).toHaveCount(0);

  // 결제 후(유료 이용권): 같은 화면이 AI 추천 + 남은 양으로 바뀐다. 링크는 사라진다.
  await page.route("**/api/auth/me", (r) => r.fulfill({ json: mePaid }));
  await page.route("**/api/billing/me", (r) => r.fulfill({ json: billingPaid }));
  await page.route("**/api/recommend/personal*", (r) => r.fulfill({ json: personalReco }));
  await page.goto("/?token=fake-jwt#recommend");
  await expect(s.getByText("AI 추천")).toBeVisible();
  await expect(s.getByText("이번 기간 AI 남은 양 63%")).toBeVisible();
  await expect(s.getByRole("link", { name: "AI가 고르는 추천은 요금제에서" })).toHaveCount(0);
});

test("AI 예산을 다 쓰면 추천과 대화 모두 무료 방식으로 답했다고 알린다", async ({ page }) => {
  await base(page, mePaid);
  await page.route("**/api/billing/me", (r) => r.fulfill({ json: { ...billingPaid, ai_budget_left_pct: 0 } }));
  await page.route("**/api/recommend/personal*", (r) =>
    r.fulfill({ json: { ...personalReco, source: "personal", comment: null, limit_reason: "budget", ai_budget_left_pct: 0 } })
  );
  await page.route("**/api/chat", (r) =>
    r.fulfill({
      json: chatReply({
        reply: "이번 기간 AI 사용량을 다 써서 조건 검색으로 답했어요. 치킨 · 700kcal 이하 조건으로 골랐어요.",
        limit_reached: true, limit_reason: "budget", plan: "high", ai_budget_left_pct: 0,
      }),
    })
  );
  await page.goto("/?token=fake-jwt#recommend");
  const s = page.getByRole("region", { name: "오늘 당신에겐" });
  await expect(s.getByText("이번 기간 AI 사용량을 다 써서 설정·기록으로 골랐어요.")).toBeVisible();
  await expect(s.getByText("이번 기간 AI 남은 양 0%")).toBeVisible();

  await page.getByRole("button", { name: "대화로 찾기" }).click();
  const chat = page.getByRole("region", { name: "대화로 찾기" });
  await chat.getByRole("textbox", { name: "메시지" }).fill("700kcal 이하 치킨");
  await chat.getByRole("button", { name: "보내기" }).click();
  await expect(chat.getByText("이번 기간 AI 사용량을 다 써서 조건 검색으로 답했어요.", { exact: false })).toBeVisible();
  await expect(chat.getByText("이번 기간 AI 남은 양 0%")).toBeVisible();
});

test("이용 중인 요금제는 연장만 되고 다른 요금제 버튼은 비활성이다", async ({ page }) => {
  await base(page, mePaid);
  await page.route("**/api/billing/me", (r) => r.fulfill({ json: billingPaid }));
  await page.goto("/?token=fake-jwt#plans");
  await expect(page.getByText(/지금 요금제/)).toContainText("High");
  await expect(page.getByText(/지금 요금제/)).toContainText("이번 기간 AI 남은 양 63%");
  await expect(page.getByRole("button", { name: "30일 연장" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Standard 시작" })).toBeDisabled();
});
