// "대화로 찾기" (3단계 챗봇). 지키는 것:
// (1) 로그인 안 했으면 칸이 없다
// (2) 무료는 "조건 검색", premium 은 "AI 대화"로 누가 답하는지 밝힌다
// (3) 조건은 브라우저가 들고 다닌다 -- 다음 말에 이전 조건을 실어 보내고, 칩 X 는 remove 로 보낸다
// (4) premium 은 이전 대화를 history 로 보낸다
// (5) 실패하면 입력한 말을 잃지 않는다
import { expect, test } from "@playwright/test";
import { authStatusOn, chatFilters, chatReply, emptyProfile, me, mePremium, mockApi } from "./fixtures";

async function loggedIn(page, user = me) {
  await mockApi(page);
  await page.route("**/api/recommend/goals", (r) => r.fulfill({ json: [{ key: "diet", label: "다이어트" }] }));
  await page.route("**/api/recommend/menus?*", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/auth/status", (r) => r.fulfill({ json: authStatusOn }));
  await page.route("**/api/auth/me", (r) => r.fulfill({ json: user }));
  await page.route("**/api/profile", (r) => r.fulfill({ json: emptyProfile }));
  const bodies = [];
  await page.route("**/api/chat", (r) => {
    const body = r.request().postDataJSON();
    bodies.push(body);
    if (body.remove === "group:치킨") {
      return r.fulfill({
        json: chatReply({
          reply: "700kcal 이하 조건으로 골랐어요.",
          filters: chatFilters({ max_calorie: 700 }),
          chips: [{ key: "kcal", label: "700kcal 이하" }],
        }),
      });
    }
    r.fulfill({ json: chatReply(user.plan === "premium" ? { source: "llm", reply: "가볍게 치킨으로 골라봤어요." } : {}) });
  });
  return bodies;
}

const panel = (page) => page.getByRole("region", { name: "대화로 찾기" });

test("로그인 안 했으면 대화 칸이 없다", async ({ page }) => {
  await mockApi(page);
  await page.route("**/api/recommend/goals", (r) => r.fulfill({ json: [{ key: "diet", label: "다이어트" }] }));
  await page.route("**/api/recommend/menus?*", (r) => r.fulfill({ json: [] }));
  await page.goto("/#recommend");
  await expect(page.getByRole("heading", { name: "맞춤 추천" })).toBeVisible();
  await expect(panel(page)).toHaveCount(0);
});

test("무료: 예시를 누르면 조건으로 골라 주고 조건 칩을 보여준다", async ({ page }) => {
  const bodies = await loggedIn(page);
  await page.goto("/?token=fake-jwt#recommend");
  const p = panel(page);
  await expect(p.getByText("조건 검색")).toBeVisible();
  await p.getByRole("button", { name: "700kcal 이하 치킨" }).click();
  await expect(p.getByText("치킨 · 700kcal 이하 조건으로 골랐어요.")).toBeVisible();
  await expect(p.getByRole("article")).toHaveCount(3);
  await expect(p.getByRole("button", { name: "치킨 조건 지우기" })).toBeVisible();
  expect(bodies[0]).toMatchObject({ message: "700kcal 이하 치킨", filters: null, remove: null });
});

test("다음 말에는 이전 조건을 싣고, 칩 X 는 remove 로 보낸다", async ({ page }) => {
  const bodies = await loggedIn(page);
  await page.goto("/?token=fake-jwt#recommend");
  const p = panel(page);
  await p.getByRole("textbox", { name: "메시지" }).fill("700kcal 이하 치킨");
  await p.getByRole("button", { name: "보내기" }).click();
  await expect(p.getByRole("button", { name: "치킨 조건 지우기" })).toBeVisible();

  await p.getByRole("textbox", { name: "메시지" }).fill("매운 거 말고");
  await p.getByRole("button", { name: "보내기" }).click();
  await expect.poll(() => bodies.length).toBe(2);
  expect(bodies[1].filters).toEqual(chatFilters({ include_groups: ["치킨"], max_calorie: 700 }));

  await p.getByRole("button", { name: "치킨 조건 지우기" }).click();
  await expect.poll(() => bodies.length).toBe(3);
  expect(bodies[2]).toMatchObject({ message: "", remove: "group:치킨" });
  await expect(p.getByRole("button", { name: "치킨 조건 지우기" })).toHaveCount(0);
  await expect(p.getByRole("button", { name: "700kcal 이하 조건 지우기" })).toBeVisible();
});

test("premium 은 AI 대화로 표시되고 이전 대화를 함께 보낸다", async ({ page }) => {
  const bodies = await loggedIn(page, mePremium);
  await page.goto("/?token=fake-jwt#recommend");
  const p = panel(page);
  await expect(p.getByText("AI 대화")).toBeVisible();
  await p.getByRole("textbox", { name: "메시지" }).fill("어제 과식했어");
  await p.getByRole("button", { name: "보내기" }).click();
  await expect(p.getByText("가볍게 치킨으로 골라봤어요.")).toBeVisible();
  await p.getByRole("textbox", { name: "메시지" }).fill("치킨 말고");
  await p.getByRole("button", { name: "보내기" }).click();
  await expect.poll(() => bodies.length).toBe(2);
  expect(bodies[1].history).toEqual([
    { role: "user", text: "어제 과식했어" },
    { role: "assistant", text: "가볍게 치킨으로 골라봤어요." },
  ]);
});

test("실패하면 안내하고 입력한 말은 입력칸에 남는다", async ({ page }) => {
  await loggedIn(page);
  await page.route("**/api/chat", (r) => r.fulfill({ status: 500, json: { detail: "x" } }));
  await page.goto("/?token=fake-jwt#recommend");
  const p = panel(page);
  const box = p.getByRole("textbox", { name: "메시지" });
  await box.fill("치킨");
  await p.getByRole("button", { name: "보내기" }).click();
  await expect(p.getByText("답을 받지 못했습니다")).toBeVisible();
  await expect(box).toHaveValue("치킨");
  await expect(p.locator(".chat-user")).toHaveCount(0); // 보내지 못한 말은 대화에 남기지 않는다
});
