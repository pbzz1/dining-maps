// 로그인은 순수 추가 기능이다 -- 이 스펙이 지키는 건 두 가지다.
// (1) 로그인이 꺼져 있거나 안 했을 때 기존 화면이 그대로일 것
// (2) 로그인하면 브라우저에 쌓여 있던 추천 설정이 서버로 한 번 올라갈 것
import { expect, test } from "@playwright/test";
import { authStatusOn, emptyProfile, me, mockApi } from "./fixtures";

const recommendMock = async (page) => {
  await page.route("**/api/recommend/goals", (r) => r.fulfill({ json: [{ key: "diet", label: "다이어트" }] }));
  await page.route("**/api/recommend/menus?*", (r) => r.fulfill({ json: [] }));
};

test("로그인이 꺼져 있으면 로그인 버튼이 아예 없다", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await expect(page.getByRole("button", { name: "카카오로 로그인" })).toHaveCount(0);
});

test("로그인이 켜져 있으면 로그인 버튼이 보인다", async ({ page }) => {
  await mockApi(page);
  await page.route("**/api/auth/status", (r) => r.fulfill({ json: authStatusOn }));
  await page.goto("/");
  await expect(page.getByRole("button", { name: "카카오로 로그인" })).toBeVisible();
});

test("콜백 토큰을 받으면 주소창에서 지우고 닉네임을 띄운다", async ({ page }) => {
  await mockApi(page);
  await recommendMock(page);
  await page.route("**/api/auth/status", (r) => r.fulfill({ json: authStatusOn }));
  await page.route("**/api/auth/me", (r) => r.fulfill({ json: me }));
  await page.route("**/api/profile", (r) => r.fulfill({ json: emptyProfile }));

  await page.goto("/?token=fake-jwt#recommend");
  await expect(page.getByRole("link", { name: /테스트유저/ })).toBeVisible();
  // 토큰이 주소에 남으면 링크를 공유하는 순간 계정이 넘어간다. 해시는 라우팅이라 살아 있어야 한다.
  await expect(page).toHaveURL(/#recommend$/);
  expect(page.url()).not.toContain("token=");
});

test("첫 로그인이면 브라우저에 있던 설정이 서버로 올라간다", async ({ page }) => {
  await mockApi(page);
  await recommendMock(page);
  await page.route("**/api/auth/status", (r) => r.fulfill({ json: authStatusOn }));
  await page.route("**/api/auth/me", (r) => r.fulfill({ json: me }));

  const uploaded = [];
  await page.route("**/api/profile", (r) => {
    if (r.request().method() === "PUT") {
      uploaded.push(r.request().postDataJSON());
      return r.fulfill({ json: r.request().postDataJSON() });
    }
    return r.fulfill({ json: emptyProfile }); // 서버는 아직 빈 프로필
  });

  // 로그인 전부터 이 브라우저에 쌓여 있던 설정
  await page.addInitScript(() => {
    localStorage.setItem("recommend.prefs", JSON.stringify({ goal: "protein", maxCalorie: 700, maxSodium: "", excludeDrinks: true }));
  });

  await page.goto("/?token=fake-jwt#recommend");
  await expect.poll(() => uploaded.length, { timeout: 5000 }).toBeGreaterThan(0);
  expect(uploaded[0].goal).toBe("protein");
  expect(uploaded[0].max_calorie).toBe(700);
  expect(uploaded[0].exclude_drinks).toBe(true);
});
