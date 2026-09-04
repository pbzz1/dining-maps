# Playwright E2E 4일 학습·구현 계획

면접 답변 초안을 실제 경험으로 바꾸기 위한 순서. 언어는 JavaScript(앱 코드베이스가 JS), 스펙 위치는 `frontend-react/tests/e2e/`.

## 초안과 실제 앱의 차이 (먼저 고칠 것)

- "브랜드 선택 → 메뉴 목록 → 영양정보 비교"는 없다. 실제 흐름: `#list` 탭 → 매장 카드 클릭 → MenuView(등급 칩 + 메뉴 리스트 + 정렬 select).
- "브랜드 마커 렌더링"은 Kakao SDK 오버레이라 DOM으로 잡기 어렵다. 지도 화면 상태 문구 "주변 매장 N곳 중…"을 검증한다.
- 빈 응답 문구는 이미 있다. 목록: "표시할 매장이 없습니다.", 지도: "주변에 매장이 없습니다." `page.route()`로 `[]`를 준다.
- 테스트 인프라·PR 워크플로우 모두 없다. 새로 만든다.
- 매장 카드가 onClick 달린 div라 `getByRole('button')`로 안 잡힌다 → `role="button"` 추가. 테스트 때문에 접근성이 좋아진 사례.

## Day 1: 설치와 감 잡기 (2시간)

```bash
cd frontend-react && npm init playwright@latest
```

- 언어 JavaScript, 테스트 폴더 `tests/e2e`, GitHub Actions 예, 브라우저 설치 예.
- `npx playwright codegen http://localhost:5173`으로 앱을 클릭해 보며 코드젠이 `getByRole`, `getByText`를 기본으로 뽑는 걸 확인.
- docs 읽기: Writing tests, Locators, Auto-waiting 세 페이지만.

## Day 2: 스펙 3개 작성 (반나절)

백엔드 없이 돌게 API를 전부 mock한다 (CI에서 DB 없이 돌기 위함).

```js
// tests/e2e/list-to-menu.spec.js
import { test, expect } from "@playwright/test";

const restaurants = [{ id: 1, name: "맥도날드", absolute_grade: "B", relative_grade: "A" }];

test.beforeEach(async ({ page }) => {
  await page.route("**/api/stats/quality", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/restaurants", (r) => r.fulfill({ json: restaurants }));
});

test("매장 카드를 누르면 메뉴 화면으로 간다", async ({ page }) => {
  await page.route("**/api/restaurants/1/**", (r) => r.fulfill({ json: [] }));
  await page.goto("/#list");
  await page.getByRole("heading", { name: "매장 선택" }).waitFor();
  await page.getByText("맥도날드").click();
  await expect(page.getByRole("heading", { name: "맥도날드" })).toBeVisible();
  await expect(page.getByRole("button", { name: "매장 목록으로" })).toBeVisible();
});

test("매장이 0건이면 안내 문구가 뜬다", async ({ page }) => {
  await page.route("**/api/restaurants", (r) => r.fulfill({ json: [] }));
  await page.goto("/#list");
  await expect(page.getByText("표시할 매장이 없습니다.")).toBeVisible();
});
```

- `/api/restaurants/1/**` mock은 stats·menu·diet-grade 세 요청의 실제 응답 형태에 맞춘다. 브라우저 네트워크 탭에서 실제 JSON을 복사해 fixture로.
- 세 번째 스펙: 지도 탭에서 `/api/stores`를 mock하고 "주변 매장 1곳" 문구 확인.
- `playwright.config.js`의 `webServer`에 `command: "npm run dev"`, `url: "http://localhost:5173"`.

## Day 3: "배운 점" 두 개를 일부러 겪기 (2시간)

- 매장 카드를 `page.locator(".restaurant-card")`로 잡아본 뒤 `role="button"` 추가 → `getByRole`로 바꾼다. 커밋을 남겨 면접에서 가리킨다.
- 지도 스펙에 `waitForTimeout(2000)`을 넣고 `npx playwright test --repeat-each 5`로 flaky를 확인한 뒤 `expect(...).toBeVisible()`로 바꾼다.

## Day 4: CI (1시간)

- `.github/workflows/e2e.yml`: `on: pull_request`, `paths: ['frontend-react/**']`, `working-directory: frontend-react`.
- 지도 스펙용 `VITE_KAKAO_JS_KEY: ${{ secrets.VITE_KAKAO_JS_KEY }}` (deploy.yml에 이미 등록된 secret 재사용).
- 실패 시 `playwright-report`를 `actions/upload-artifact`로 업로드.

## 면접 답변 수정본

> dining-maps 프론트엔드 E2E로 쓰고 있고, `tests/e2e/`에 스펙 3개, 케이스 5개입니다. 시나리오는 지도 첫 로딩 후 주변 매장 상태 문구, 매장 목록에서 카드 선택 → 메뉴·등급 화면 진입, 그리고 API가 빈 배열을 줄 때 안내 문구가 뜨는지 이렇게 정상/예외로 나눴습니다. 백엔드는 `page.route`로 mock해서 CI에서 DB 없이 돌게 했습니다.
>
> 배운 건 두 가지입니다. 매장 카드가 onClick 달린 div라 `getByRole`로 안 잡혀서 `role="button"`을 붙였는데, 테스트 때문에 접근성이 같이 좋아진 경우였습니다. 그리고 카카오 지도가 비동기라 `waitForTimeout`을 썼다가 `--repeat-each`로 돌려보니 flaky해서 `expect().toBeVisible()` auto-wait로 바꿨습니다.
>
> 로컬과 PR 워크플로우에서 돌고, 실패하면 HTML 리포트를 아티팩트로 올립니다. Allure는 다음 단계로 보고 있습니다.
