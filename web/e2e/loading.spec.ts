import { expect, test, type Route } from "@playwright/test";

// The unified loading language (features/loading): never a blank screen while data is on its way.
// Read-only checks on the AI workspace; responses are held back with page.route to see the wait.
test.use({ baseURL: "http://127.0.0.1:8798" });

// holds matching requests until release(); `abort` drops them instead (keeps the workspace unchanged)
const hold = (abort = false) => {
  let release!: () => void;
  const gate = new Promise<void>((r) => (release = r));
  return { release, wait: (route: Route) => gate.then(() => (abort ? route.abort() : route.continue())) };
};

test("home shows episode placeholders until the list arrives", async ({ page }) => {
  const h = hold();
  await page.route("**/api/episodes", h.wait);
  await page.goto("/#/");
  await expect(page.getByTestId("episodes-loading")).toBeVisible();
  await expect(page.getByTestId("episodes-loading").locator("li")).toHaveCount(3);
  await expect(page.getByTestId("top-line")).toHaveAttribute("data-on", "0"); // a GET list load uses placeholders, not the line
  h.release();
  await expect(page.getByTestId("episodes-loading")).toHaveCount(0);
  await expect(page.locator(".ep-list li a").first()).toBeVisible();
});

test("opening an episode and a tab shows what is opening, then the page", async ({ page }) => {
  const h = hold();
  await page.route(/\/api\/episodes\/[^/]+$/, h.wait);
  await page.goto("/");
  const loading = page.getByTestId("page-loading");
  await expect(loading).toContainText("正在打开这一集…");
  await expect(page.getByTestId("top-line")).toHaveAttribute("data-on", "1");
  h.release();
  await expect(loading).toHaveCount(0);
  await expect(page.getByTestId("top-line")).toHaveAttribute("data-on", "0");

  const p = hold();
  await page.route(/\/api\/episodes\/[^/]+\/publish$/, p.wait);
  await page.getByRole("link", { name: "发布", exact: true }).click();
  await expect(loading).toContainText("正在打开发布资料…");
  p.release();
  await expect(page.getByRole("heading", { name: "发布资料", exact: true })).toBeVisible();
  await expect(loading).toHaveCount(0);
});

test("an action the person started moves the top line until it answers", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/#\/ep\/.+\/listen/, { timeout: 20_000 });
  const h = hold(true);
  await page.route(/\/api\/episodes\/[^/]+\/chat$/, (route) => (route.request().method() === "POST" ? h.wait(route) : route.continue()));
  await page.getByLabel("对 LACUNA 说（从当前播放位置开始）").fill("这里停顿太长");
  await page.getByLabel("对 LACUNA 说（从当前播放位置开始）").press("Enter");
  await expect(page.getByTestId("waiting")).toContainText("已用");
  await expect(page.getByTestId("top-line")).toHaveAttribute("data-on", "1");
  h.release();
  await expect(page.getByTestId("waiting")).toHaveCount(0);
  await expect(page.getByTestId("top-line")).toHaveAttribute("data-on", "0");
});
