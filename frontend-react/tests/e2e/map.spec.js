// 지도 첫 로딩: 카카오 SDK가 뜨고 주변 매장을 불러와 상태 문구에 반영한다
import { test, expect } from "@playwright/test";
import { mockApi } from "./fixtures";

test("지도 첫 진입 시 주변 매장 수가 상태 문구에 뜬다", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  // 위치 권한은 기본 거부 -> 서울시청 기준으로 조회된다 (MapView의 fallback 경로)
  await expect(page.getByText("주변 매장 1곳 중 다이어트 추천 상위 1곳")).toBeVisible();
});
