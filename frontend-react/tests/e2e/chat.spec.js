// "대화로 찾기" (3단계 챗봇). 어느 탭에서든 오른쪽 아래 떠 있는 단추로 연다. 지키는 것:
// (0) 단추는 지도 탭에선 숨고, 서버 로그인이 꺼져 있으면 아예 없다. 닫았다 열어도 대화가 남는다
// (1) 로그인 안 했으면 대화 대신 로그인 안내
// (2) 무료는 "조건 검색", premium 은 "AI 대화"로 누가 답하는지 밝힌다
// (3) 조건은 브라우저가 들고 다닌다 -- 다음 말에 이전 조건을 실어 보내고, 칩 X 는 remove 로 보낸다
// (4) premium 은 이전 대화를 history 로 보낸다
// (5) 실패하면 입력한 말을 잃지 않는다
import { expect, test } from "@playwright/test";
import { authStatusOff, authStatusOn, chatFilters, chatReply, emptyProfile, me, mePremium, mockApi } from "./fixtures";

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
    r.fulfill({ json: chatReply(user.plan !== "free" ? { source: "llm", reply: "가볍게 치킨으로 골라봤어요.", plan: user.plan, ai_budget_left_pct: 63 } : {}) });
  });
  return bodies;
}

const panel = (page) => page.getByRole("region", { name: "대화로 찾기" });

const fab = (page) => page.getByRole("button", { name: "대화로 찾기" });

// 홈(신메뉴)에서 연다 -- 맞춤 추천 탭에 가지 않아도 쓸 수 있다는 게 이 단추의 요지.
async function openChat(page, url = "/?token=fake-jwt") {
  await page.goto(url);
  await fab(page).click();
  return panel(page);
}

async function loggedOut(page, status = authStatusOn) {
  await mockApi(page);
  await page.route("**/api/recommend/goals", (r) => r.fulfill({ json: [{ key: "diet", label: "다이어트" }] }));
  await page.route("**/api/recommend/menus?*", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/auth/status", (r) => r.fulfill({ json: status }));
}

test("로그인 안 했으면 열어도 대화 대신 로그인 안내가 뜬다", async ({ page }) => {
  await loggedOut(page);
  const p = await openChat(page, "/");
  await expect(p.getByRole("button", { name: "카카오로 로그인" })).toBeVisible();
  await expect(p.getByRole("textbox", { name: "메시지" })).toHaveCount(0);
});

test("서버에 로그인이 꺼져 있으면 단추가 없다", async ({ page }) => {
  await loggedOut(page, authStatusOff);
  const status = page.waitForResponse("**/api/auth/status");
  await page.goto("/");
  await status;
  await expect(page.getByRole("heading", { name: "신메뉴" })).toBeVisible();
  await expect(fab(page)).toHaveCount(0);
});

test("맞춤 추천 탭 안에는 대화 칸이 없고, 지도 탭에선 단추가 숨는다", async ({ page }) => {
  await loggedIn(page);
  await page.goto("/?token=fake-jwt#recommend");
  await expect(fab(page)).toBeVisible();
  await expect(panel(page)).toHaveCount(0);
  await page.getByRole("button", { name: "지도" }).click();
  await expect(fab(page)).toBeHidden();
  await page.getByRole("button", { name: "신메뉴" }).click();
  await expect(fab(page)).toBeVisible();
});

test("닫았다 다시 열어도 대화가 남고, 닫으면 단추로 포커스가 돌아온다", async ({ page }) => {
  await loggedIn(page);
  const p = await openChat(page);
  await expect(p.getByRole("textbox", { name: "메시지" })).toBeFocused();
  await p.getByRole("button", { name: "700kcal 이하 치킨" }).click();
  await expect(p.getByText("치킨 · 700kcal 이하 조건으로 골랐어요.")).toBeVisible();
  await p.getByRole("button", { name: "대화 닫기" }).click();
  await expect(panel(page)).toBeHidden();
  await expect(fab(page)).toBeFocused();
  await fab(page).click();
  await expect(p.getByText("치킨 · 700kcal 이하 조건으로 골랐어요.")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(panel(page)).toBeHidden();
});

test("무료: 예시를 누르면 조건으로 골라 주고 조건 칩을 보여준다", async ({ page }) => {
  const bodies = await loggedIn(page);
  const p = await openChat(page);
  await expect(p.getByText("조건 검색")).toBeVisible();
  await p.getByRole("button", { name: "700kcal 이하 치킨" }).click();
  await expect(p.getByText("치킨 · 700kcal 이하 조건으로 골랐어요.")).toBeVisible();
  await expect(p.getByRole("article")).toHaveCount(3);
  await expect(p.getByRole("button", { name: "치킨 조건 지우기" })).toBeVisible();
  expect(bodies[0]).toMatchObject({ message: "700kcal 이하 치킨", filters: null, remove: null });
});

test("다음 말에는 이전 조건을 싣고, 칩 X 는 remove 로 보낸다", async ({ page }) => {
  const bodies = await loggedIn(page);
  const p = await openChat(page);
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
  const p = await openChat(page);
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
  const p = await openChat(page);
  const box = p.getByRole("textbox", { name: "메시지" });
  await box.fill("치킨");
  await p.getByRole("button", { name: "보내기" }).click();
  await expect(p.getByText("답을 받지 못했습니다")).toBeVisible();
  await expect(box).toHaveValue("치킨");
  await expect(p.locator(".chat-user")).toHaveCount(0); // 보내지 못한 말은 대화에 남기지 않는다
});
