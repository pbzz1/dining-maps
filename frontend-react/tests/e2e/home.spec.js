// 기본 화면이 지도에서 신메뉴로 바뀐 것: 홈에서는 지도 관련 요청이 전혀 나가지 않고,
// 사이드바 순서도 신메뉴가 맨 앞이다.
import { test, expect } from "@playwright/test";
import { mockApi } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

test("루트로 들어가면 신메뉴 화면이 기본으로 뜬다", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "신메뉴" })).toBeVisible();
  await expect(page.getByText("두부 포케볼")).toBeVisible();
});

test("홈에서는 매장 API가 나가지 않고, 지도 탭을 열어야 매장이 뜬다", async ({ page }) => {
  let storesRequested = false;
  page.on("request", (req) => {
    if (req.url().includes("/api/stores")) storesRequested = true;
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "신메뉴" })).toBeVisible();
  expect(storesRequested).toBe(false);

  await page.getByRole("button", { name: "지도" }).click();
  await expect(page.locator(".store-card")).toHaveCount(1);
});

test("사이드바 탭 순서가 신메뉴 우선으로 바뀌었다", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator(".nav-btn")).toHaveText(["신메뉴", "맞춤 추천", "지도", "대시보드", "매장 목록"]);
});
