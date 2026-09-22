// 지도 첫 로딩: 카카오 SDK가 뜨고 주변 매장을 불러와 목록에 반영한다
import { test, expect } from "@playwright/test";
import { mockApi } from "./fixtures";

test("지도 첫 진입 시 주변 매장이 목록에 뜬다", async ({ page }) => {
  await mockApi(page);
  // 지도는 더 이상 홈이 아니다 -- "#map"으로 직접 연다 (공유 링크와 같은 경로).
  await page.goto("/#map");
  // 위치 권한은 기본 거부 -> 서울시청 기준으로 조회된다 (MapView의 fallback 경로)
  await expect(page.locator(".store-card")).toHaveCount(1);
});
