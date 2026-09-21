// "AI가 기억하는 것" (premium AI 메모리). 지키는 것:
// (1) premium 은 기억 목록을 보고, 지우고, 직접 적을 수 있다 -- 무엇을 믿고 추천하는지 보여야 한다
// (2) 추천이 새로 기억하면 그 자리에서 "기억해 둘게요"로 알리고 목록이 늘어난다
// (3) free 는 기억이 없으면 패널이 없고, 남아 있으면 보고 지울 수만 있다(추가 칸 없음)
import { expect, test } from "@playwright/test";
import { authStatusOn, emptyProfile, me, memoryList, mePremium, mockApi, personalReco } from "./fixtures";

async function loggedIn(page, user, memory) {
  await mockApi(page);
  await page.route("**/api/recommend/goals", (r) => r.fulfill({ json: [{ key: "diet", label: "다이어트" }] }));
  await page.route("**/api/recommend/menus?*", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/auth/status", (r) => r.fulfill({ json: authStatusOn }));
  await page.route("**/api/auth/me", (r) => r.fulfill({ json: user }));
  await page.route("**/api/profile", (r) => r.fulfill({ json: emptyProfile }));
  let list = [...memory];
  const calls = { post: [], del: [] };
  await page.route("**/api/memory", (r) => {
    if (r.request().method() === "POST") {
      const { fact } = r.request().postDataJSON();
      calls.post.push(fact);
      list = [...list, { id: 99, fact, source: "user", created_at: "2026-01-04T00:00:00Z" }];
      return r.fulfill({ status: 201, json: list });
    }
    return r.fulfill({ json: list });
  });
  await page.route("**/api/memory/*", (r) => {
    const id = Number(r.request().url().split("/").pop());
    calls.del.push(id);
    list = list.filter((m) => m.id !== id);
    r.fulfill({ status: 204 });
  });
  return { calls, add: (m) => (list = [...list, m]) };
}

const panel = (page) => page.locator("details", { hasText: "AI가 기억하는 것" });

test("premium 은 기억 목록을 펼쳐 보고 지울 수 있다", async ({ page }) => {
  const { calls } = await loggedIn(page, mePremium, memoryList);
  await page.goto("/?token=fake-jwt#recommend");
  const p = panel(page);
  await expect(p.getByText("2개")).toBeVisible();
  await p.getByText("AI가 기억하는 것").click();
  await expect(p.getByText("매운 양념 메뉴는 자주 뺀다")).toBeVisible();
  await expect(p.getByText("AI가 알아냄")).toBeVisible();
  await expect(p.getByText("직접 적음")).toBeVisible();

  await p.getByRole("button", { name: '"매운 양념 메뉴는 자주 뺀다" 지우기' }).click();
  await expect(p.getByText("매운 양념 메뉴는 자주 뺀다")).toHaveCount(0);
  await expect.poll(() => calls.del).toEqual([1]);
});

test("premium 은 직접 한 줄을 적어 기억시킬 수 있다", async ({ page }) => {
  const { calls } = await loggedIn(page, mePremium, []);
  await page.goto("/?token=fake-jwt#recommend");
  const p = panel(page);
  await p.getByText("AI가 기억하는 것").click();
  const add = p.getByRole("button", { name: "추가" });
  await expect(add).toBeDisabled(); // 빈 칸으로는 못 보낸다
  await p.getByLabel("직접 알려주기").fill("저녁은 가볍게 먹어요");
  await add.click();
  await expect(p.getByText("저녁은 가볍게 먹어요")).toBeVisible();
  await expect(p.getByLabel("직접 알려주기")).toHaveValue("");
  expect(calls.post).toEqual(["저녁은 가볍게 먹어요"]);
});

test("추천이 새로 기억하면 그 자리에서 알리고 목록이 늘어난다", async ({ page }) => {
  const mem = await loggedIn(page, mePremium, []);
  let remembered = false;
  await page.route("**/api/recommend/personal*", (r) => {
    // 서버처럼: 처음 한 번만 새로 기억하고(같은 사실은 UNIQUE 로 다시 안 들어간다) 그때만 알린다.
    // 첫 로그인은 설정 업로드 뒤 한 번 더 불러오는 게 정상이라 호출은 2번 온다.
    const fresh = !remembered;
    if (fresh) mem.add({ id: 7, fact: "샐러드를 자주 저장한다", source: "ai", created_at: "2026-01-05T00:00:00Z" });
    remembered = true;
    r.fulfill({ json: { ...personalReco, memory_added: fresh ? ["샐러드를 자주 저장한다"] : [] } });
  });
  await page.goto("/?token=fake-jwt#recommend");
  await expect(page.getByText("기억해 둘게요: 샐러드를 자주 저장한다")).toBeVisible();
  await expect(panel(page).getByText("1개")).toBeVisible();
});

test("free 는 기억이 없으면 패널이 없다", async ({ page }) => {
  await loggedIn(page, me, []);
  await page.goto("/?token=fake-jwt#recommend");
  await expect(page.getByRole("region", { name: "오늘 당신에겐" })).toBeVisible();
  await expect(panel(page)).toHaveCount(0);
});

test("free 로 내려가도 남은 기억은 보고 지울 수 있지만 추가 칸은 없다", async ({ page }) => {
  await loggedIn(page, me, memoryList);
  await page.goto("/?token=fake-jwt#recommend");
  const p = panel(page);
  await p.getByText("AI가 기억하는 것").click();
  await expect(p.getByText("점심은 회사 근처에서 먹는다")).toBeVisible();
  await expect(p.getByRole("button", { name: /지우기/ }).first()).toBeVisible();
  await expect(p.getByLabel("직접 알려주기")).toHaveCount(0);
});
