// 모바일(375px): 화면이 옆으로 밀리지 않고, 뷰가 죽지 않는다.
// .view-wrap/.map-view가 각자 스크롤 컨테이너라 document.scrollWidth로는 안 잡힌다 -- 컨테이너 기준으로 본다.
import { test, expect } from "@playwright/test";
import { mockApi } from "./fixtures";

test.use({ viewport: { width: 375, height: 812 } });

const overflowing = (page) =>
  page.evaluate(() =>
    [...document.querySelectorAll("main, .view-wrap, .map-view")]
      .filter((el) => el.offsetWidth && el.scrollWidth > el.clientWidth + 1)
      .map((el) => `${el.className} ${el.scrollWidth}>${el.clientWidth}`)
  );

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

test("기준 문서(#about)의 넓은 표는 표 안에서만 스크롤된다", async ({ page }) => {
  await page.goto("/#about");
  await expect(page.getByRole("heading", { name: "식사 기준 (meal)" })).toBeVisible();
  expect(await overflowing(page)).toEqual([]);
});

test("지도 탭이 화면 폭에 맞고, 매장 목록까지 스크롤해 내려갈 수 있다", async ({ page }) => {
  await page.goto("/#map");
  await expect(page.locator(".map-toolbar")).toBeVisible();
  expect(await overflowing(page)).toEqual([]);
  await page.locator(".map-toolbar").hover();
  await page.mouse.wheel(0, 3000);
  await expect(page.locator(".store-list")).toBeInViewport();
});

test("신메뉴를 먼저 봐도 맞춤 추천이 죽지 않는다", async ({ page }) => {
  // 신메뉴가 recommend.profile=null을 저장한 뒤, 맞춤 추천이 그 null을 프로필로 읽던 순서
  await page.route("**/api/new-menus*", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/recommend/*", (r) => r.fulfill({ json: [] }));
  await page.goto("/#new");
  await expect(page.getByRole("heading", { name: "신메뉴" })).toBeVisible();
  await page.goto("/#recommend");
  await page.reload();
  await expect(page.getByRole("heading", { name: "맞춤 추천" })).toBeVisible();
});
