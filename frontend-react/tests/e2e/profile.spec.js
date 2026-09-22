// 내 정보 (#me). 지키는 것:
// (1) 로그인하면 상단바 닉네임이 내 정보로 가는 링크다
// (2) 맞춤 추천에서 저장한 메뉴가 즐겨찾기 탭에 모이고, 해제하면 바로 빠지며 서버에 DELETE 가 나간다
// (3) 저장한 게 없으면 어디서 저장하는지 알려 준다. 로그인 안 했으면 로그인을 권한다
// (4) 이미 저장한 메뉴는 추천 카드에서도 "저장됨"으로 뜨고, 다시 누르면 해제된다
// (5) 내 정보에서 해제하고 맞춤 추천으로 돌아오면 새로고침 없이 "저장"으로 돌아와 있다
import { expect, test } from "@playwright/test";
import { authStatusOn, emptyProfile, favorites, me, mockApi, personalReco } from "./fixtures";

async function loggedIn(page, favs = favorites) {
  await mockApi(page);
  await page.route("**/api/auth/status", (r) => r.fulfill({ json: authStatusOn }));
  await page.route("**/api/auth/me", (r) => r.fulfill({ json: me }));
  await page.route("**/api/profile", (r) => r.fulfill({ json: emptyProfile }));
  const deleted = [];
  await page.route("**/api/favorites", (r) => r.fulfill({ json: favs }));
  await page.route("**/api/favorites/*", (r) => {
    deleted.push(Number(r.request().url().split("/").pop()));
    r.fulfill({ status: 204 });
  });
  return deleted;
}

test("닉네임을 누르면 내 정보의 즐겨찾기가 열린다", async ({ page }) => {
  await loggedIn(page);
  await page.goto("/?token=fake-jwt");
  await page.getByRole("link", { name: /테스트유저/ }).click();
  await expect(page).toHaveURL(/#me$/);
  await expect(page.getByRole("heading", { name: "테스트유저" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "즐겨찾기" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("article")).toHaveCount(2);
  await expect(page.getByText("샐러디 · 치킨 샐러드")).toBeVisible();
});

test("즐겨찾기 해제는 바로 빠지고 서버에 기록된다", async ({ page }) => {
  const deleted = await loggedIn(page);
  await page.goto("/?token=fake-jwt#me");
  await page.getByRole("button", { name: "샐러디 치킨 샐러드 즐겨찾기 해제" }).click();
  await expect(page.getByRole("article")).toHaveCount(1);
  await expect.poll(() => deleted).toEqual([201]);
});

test("저장한 게 없으면 맞춤 추천으로 안내한다", async ({ page }) => {
  await loggedIn(page, []);
  await page.goto("/?token=fake-jwt#me");
  await expect(page.getByText("아직 저장한 메뉴가 없어요.")).toBeVisible();
  await expect(page.getByRole("link", { name: "맞춤 추천" })).toHaveAttribute("href", "#recommend");
});

test("계정 탭에서 로그아웃하면 로그인 안내로 바뀐다", async ({ page }) => {
  await loggedIn(page);
  await page.goto("/?token=fake-jwt#me");
  await page.getByRole("tab", { name: "계정" }).click();
  await page.getByRole("button", { name: "로그아웃" }).click();
  await expect(page.getByRole("heading", { name: "내 정보" })).toBeVisible();
  await expect(page.getByRole("link", { name: /테스트유저/ })).toHaveCount(0);
});

test("로그인 안 했으면 로그인을 권한다", async ({ page }) => {
  await mockApi(page);
  await page.route("**/api/auth/status", (r) => r.fulfill({ json: authStatusOn }));
  await page.goto("/#me");
  await expect(page.getByRole("heading", { name: "내 정보" })).toBeVisible();
  await expect(page.getByRole("main").getByRole("button", { name: "카카오로 로그인" })).toBeVisible();
});

test("이미 저장한 추천 카드는 저장됨으로 뜨고, 다시 누르면 해제된다", async ({ page }) => {
  const saved = [{ ...favorites[0], menu_item_id: personalReco.items[0].menu_item_id }];
  const deleted = await loggedIn(page, saved);
  await page.route("**/api/recommend/goals", (r) => r.fulfill({ json: [{ key: "diet", label: "다이어트" }] }));
  await page.route("**/api/recommend/menus?*", (r) => r.fulfill({ json: [] }));
  await page.goto("/?token=fake-jwt#recommend");
  const s = page.getByRole("region", { name: "오늘 당신에겐" });
  const first = s.getByRole("article").first().getByRole("button", { name: "저장됨" });
  await expect(first).toHaveAttribute("aria-pressed", "true");
  await first.click();
  await expect(s.getByRole("article").first().getByRole("button", { name: "저장", exact: true })).toBeVisible();
  await expect.poll(() => deleted).toEqual([personalReco.items[0].menu_item_id]);
});

test("내 정보에서 해제하고 맞춤 추천으로 돌아오면 카드가 저장으로 돌아와 있다", async ({ page }) => {
  const id = personalReco.items[0].menu_item_id;
  await loggedIn(page, [{ ...favorites[0], menu_item_id: id }]);
  await page.route("**/api/recommend/goals", (r) => r.fulfill({ json: [{ key: "diet", label: "다이어트" }] }));
  await page.route("**/api/recommend/menus?*", (r) => r.fulfill({ json: [] }));
  await page.goto("/?token=fake-jwt#recommend");
  const card = page.getByRole("region", { name: "오늘 당신에겐" }).getByRole("article").first();
  await expect(card.getByRole("button", { name: "저장됨" })).toBeVisible();

  await page.getByRole("link", { name: /테스트유저/ }).click();
  await page.getByRole("button", { name: /즐겨찾기 해제/ }).click();
  await expect(page.getByRole("button", { name: /즐겨찾기 해제/ })).toHaveCount(0);

  await page.goBack();
  await expect(page).toHaveURL(/#recommend$/);
  await expect(card.getByRole("button", { name: "저장", exact: true })).toHaveAttribute("aria-pressed", "false");
});
