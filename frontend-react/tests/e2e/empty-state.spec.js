// 예외 흐름: API가 빈 배열을 줘도 화면이 깨지지 않고 안내 문구가 뜬다
import { test, expect } from "@playwright/test";
import { mockApi } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

test("매장 목록이 0건이면 안내 문구가 뜬다", async ({ page }) => {
  await page.route("**/api/restaurants", (r) => r.fulfill({ json: [] }));
  await page.goto("/#list");
  await expect(page.getByText("표시할 매장이 없습니다.")).toBeVisible();
});

test("주변 매장이 0건이면 지도 상태 문구가 뜬다", async ({ page }) => {
  await page.route("**/api/stores?*", (r) => r.fulfill({ json: [] }));
  await page.goto("/#map");
  await expect(page.getByText("주변에 매장이 없습니다.")).toBeVisible();
});
