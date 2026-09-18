// 지도 첫 로딩: 카카오 SDK가 뜨고 주변 매장을 불러와 상태 문구에 반영한다
import { test, expect } from "@playwright/test";
import { mockApi } from "./fixtures";

test("지도 첫 진입 시 주변 매장 수가 상태 문구에 뜬다", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  // 위치 권한은 기본 거부 -> 서울시청 기준으로 조회된다 (MapView의 fallback 경로)
  await expect(page.getByText("주변 매장 1곳 중 추천 상위 1곳")).toBeVisible();
});

test("목표를 바꾸면 추천 메뉴가 그 목표 기준으로 바뀐다", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await expect(page.locator(".store-reco")).toContainText("치킨 샐러드");
  await page.getByRole("button", { name: "근성장" }).click();
  await expect(page.locator(".store-reco")).toContainText("연어 샐러드");
});

test("음식 종류를 고르면 그 종류 메뉴가 없는 브랜드는 목록에서 빠진다", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await expect(page.locator(".store-card")).toHaveCount(1);
  await page.getByRole("button", { name: "버거", exact: true }).click();
  await expect(page.locator(".store-card")).toHaveCount(0);
});
