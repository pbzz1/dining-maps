// "오늘 당신에겐" (개인 추천 AI). 지키는 것:
// (1) 로그인 안 했으면 칸도, 요청도 없다 -- 비로그인 화면은 1단계 이전 그대로
// (2) AI가 고른 3개와 한 줄 조언이 뜨고, 문장의 출처를 배지로 밝힌다
// (3) 무료(source=personal)는 "내 설정·기록 기반" 배지로 뜬다. 후보가 없으면(rule) 칸을 접는다
// (4) "이 메뉴 빼기"는 즉시 사라지고, 서버에 기록한 뒤 다시 고른다
import { expect, test } from "@playwright/test";
import { authStatusOn, emptyProfile, me, mockApi, personalReco } from "./fixtures";

async function loggedIn(page) {
  await mockApi(page);
  await page.route("**/api/recommend/goals", (r) => r.fulfill({ json: [{ key: "diet", label: "다이어트" }] }));
  await page.route("**/api/recommend/menus?*", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/auth/status", (r) => r.fulfill({ json: authStatusOn }));
  await page.route("**/api/auth/me", (r) => r.fulfill({ json: me }));
  await page.route("**/api/profile", (r) => r.fulfill({ json: emptyProfile }));
}

const section = (page) => page.getByRole("region", { name: "오늘 당신에겐" });

test("로그인 안 했으면 오늘 당신에겐 칸이 없고 요청도 나가지 않는다", async ({ page }) => {
  await mockApi(page);
  await page.route("**/api/recommend/goals", (r) => r.fulfill({ json: [{ key: "diet", label: "다이어트" }] }));
  await page.route("**/api/recommend/menus?*", (r) => r.fulfill({ json: [] }));
  let called = false;
  await page.route("**/api/recommend/personal*", (r) => {
    called = true;
    r.fulfill({ json: personalReco });
  });
  await page.goto("/#recommend");
  await expect(page.getByRole("heading", { name: "맞춤 추천" })).toBeVisible();
  await expect(section(page)).toHaveCount(0);
  expect(called).toBe(false);
});

test("로그인하면 AI가 고른 3개와 한 줄 조언이 뜬다", async ({ page }) => {
  await loggedIn(page);
  await page.goto("/?token=fake-jwt#recommend");
  const s = section(page);
  await expect(s.getByText("AI 추천")).toBeVisible();
  await expect(s.getByText(personalReco.comment)).toBeVisible();
  await expect(s.getByRole("article")).toHaveCount(3);
  await expect(s.getByText(personalReco.items[0].reason)).toBeVisible();
  await expect(page.getByRole("heading", { name: "목표 점수 순 전체" })).toBeVisible();
});

test("무료 사용자는 내 설정·기록 기반 배지로 뜬다", async ({ page }) => {
  await loggedIn(page);
  await page.route("**/api/recommend/personal*", (r) =>
    r.fulfill({ json: { ...personalReco, source: "personal", comment: null } })
  );
  await page.goto("/?token=fake-jwt#recommend");
  const s = section(page);
  await expect(s.getByText("내 설정·기록 기반")).toBeVisible();
  await expect(s.getByText("AI 추천")).toHaveCount(0);
  await expect(s.getByRole("article")).toHaveCount(3);
});

test("고를 후보가 없으면(rule) 칸을 접고 목록만 보여준다", async ({ page }) => {
  await loggedIn(page);
  let served = false;
  await page.route("**/api/recommend/personal*", (r) => {
    served = true;
    r.fulfill({ json: { source: "rule", goal: "diet", comment: null, items: [] } });
  });
  await page.goto("/?token=fake-jwt#recommend");
  await expect.poll(() => served).toBe(true);
  await expect(section(page)).toHaveCount(0);
  // 칸이 없으면 아래 목록에 구분 제목도 붙이지 않는다
  await expect(page.getByRole("heading", { name: "목표 점수 순 전체" })).toHaveCount(0);
});

test("이 메뉴 빼기를 누르면 바로 사라지고, 기록한 뒤 다시 고른다", async ({ page }) => {
  await loggedIn(page);
  const events = [];
  await page.route("**/api/events", (r) => {
    events.push(r.request().postDataJSON());
    r.fulfill({ status: 204 });
  });
  let calls = 0;
  await page.route("**/api/recommend/personal*", (r) => {
    calls += 1;
    // 서버처럼: 숨긴 메뉴는 hide 이벤트가 기록된 뒤부터 후보에서 빠진다. 호출 횟수로
    // 흉내 내면 안 된다 -- 첫 로그인은 설정 업로드 후 한 번 더 불러오는 게 정상 동작이다.
    const hidden = new Set(events.filter((e) => e.event_type === "hide").map((e) => e.menu_item_id));
    r.fulfill({ json: { ...personalReco, items: personalReco.items.filter((i) => !hidden.has(i.menu_item_id)) } });
  });
  await page.goto("/?token=fake-jwt#recommend");
  const s = section(page);
  const first = s.getByRole("article").filter({ hasText: "치킨 샐러드" });
  await expect(first).toBeVisible();
  const before = calls;

  await first.getByRole("button", { name: "이 메뉴 빼기" }).click();
  await expect(s.getByText("치킨 샐러드")).toHaveCount(0);
  await expect.poll(() => events.find((e) => e.event_type === "hide")).toEqual({ event_type: "hide", menu_item_id: 11 });
  await expect.poll(() => calls).toBeGreaterThan(before);
  await expect(s.getByText("치킨 샐러드")).toHaveCount(0);
});

test("저장을 누르면 저장됨으로 바뀌고 save 이벤트를 남긴다", async ({ page }) => {
  await loggedIn(page);
  const events = [];
  await page.route("**/api/events", (r) => {
    events.push(r.request().postDataJSON());
    r.fulfill({ status: 204 });
  });
  await page.goto("/?token=fake-jwt#recommend");
  const card = section(page).getByRole("article").filter({ hasText: "연어 샐러드" });
  await card.getByRole("button", { name: "저장" }).click();
  await expect(card.getByRole("button", { name: "저장됨" })).toHaveAttribute("aria-pressed", "true");
  await expect.poll(() => events.find((e) => e.event_type === "save")).toEqual({ event_type: "save", menu_item_id: 12 });
});
