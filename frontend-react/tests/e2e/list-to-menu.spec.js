// 정상 흐름: 매장 목록 -> 카드 클릭 -> 메뉴/등급 화면 -> 뒤로가기
import { test, expect } from "@playwright/test";
import { mockApi } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await mockApi(page);
  await page.goto("/#list");
});

test("매장 카드를 누르면 그 매장의 메뉴 화면으로 간다", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "매장 선택" })).toBeVisible();

  // ponytail: 카드가 onClick 달린 div라 role이 없다 -> 텍스트로 잡는다. Day 3에서 role="button" 붙이고 getByRole로 교체.
  await page.getByText("샐러디", { exact: true }).click();

  await expect(page.getByRole("heading", { name: "샐러디" })).toBeVisible();
  await expect(page.getByText("메뉴 2개")).toBeVisible();
  await expect(page.getByText("치킨 샐러드")).toBeVisible();
});

test("메뉴 화면에서 뒤로가기를 누르면 목록으로 돌아온다", async ({ page }) => {
  await page.getByText("샐러디", { exact: true }).click();
  await page.getByRole("button", { name: "매장 목록으로" }).click();
  await expect(page.getByRole("heading", { name: "매장 선택" })).toBeVisible();
});
