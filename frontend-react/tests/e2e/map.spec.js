// 지도 첫 로딩: 카카오 SDK가 뜨고 주변 매장을 불러와 목록에 반영한다
import { test, expect } from "@playwright/test";
import { mockApi } from "./fixtures";

test("지도 첫 진입 시 주변 매장이 목록에 뜬다", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  // 위치 권한은 기본 거부 -> 서울시청 기준으로 조회된다 (MapView의 fallback 경로)
  await expect(page.locator(".store-card")).toHaveCount(1);
});
