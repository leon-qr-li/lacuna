// 用户动态 in the admin (decision 2026-10-31-admin-user-activity): the drawer's summary leads to the full page,
// the page shows what the member did (merged, failed in red, filters), and the look lands in the audit log.
import { expect, test, type Page } from "@playwright/test";

const ADMIN = "http://admin.localhost:8799";
const OWNER = "leon@example.com";
const MEMBER = "pei@example.com";
const PW = "correct horse battery";
const SHOTS = process.env.LACUNA_SHOTS; // a folder: also save screenshots (for looking at the design)

test.beforeEach(async ({ request, page }) => {
  await request.post("/api/auth/_test/reset?skip_setup=false");
  await page.goto(ADMIN + "/");
  const seeded = await page.evaluate(async () => (await fetch("/api/admin/_test/seed", { method: "POST", headers: { "X-Lacuna-Admin": "1" } })).status);
  expect(seeded).toBe(200);
});

test.afterEach(async ({ request, page }) => {
  await page.goto(ADMIN + "/");
  await page.evaluate(async () => fetch("/api/admin/_test/clear", { method: "POST", headers: { "X-Lacuna-Admin": "1" } }));
  await request.post("/api/auth/_test/reset?skip_setup=true");
});

async function signIn(page: Page) {
  await page.goto(ADMIN + "/");
  const code = await page.evaluate(async (e) => (await (await fetch(`/api/admin/_test/code?email=${encodeURIComponent(e)}`)).json()).code, OWNER);
  await page.getByTestId("login-email").fill(OWNER);
  await page.getByTestId("login-password").fill(PW);
  await page.getByTestId("login-code").fill(code);
  await page.getByTestId("login-submit").click();
  await expect(page.getByTestId("todo")).toBeVisible();
}

test("the member's activity: drawer summary, full page with a failed change, and the look is audited", async ({ page }) => {
  // the member does something that works and something that fails, on the main site
  const member = await page.context().browser()!.newContext({ baseURL: "http://127.0.0.1:8799" });
  const m = member.request;
  expect((await m.post("/api/auth/login", { data: { email: MEMBER, password: PW } })).status()).toBe(200);
  expect((await m.post("/api/albums", { data: { name: "第一季" } })).status()).toBe(200);
  expect((await m.post("/api/episodes/EP001/manual/cut", { data: { start: 5, end: 2 } })).status()).toBe(422);
  await member.close();

  await signIn(page);
  await page.goto(ADMIN + "/users");
  await page.getByTestId("user-row").filter({ hasText: MEMBER }).click();
  const drawer = page.getByTestId("drawer-activity");
  await expect(drawer).toContainText("建了专辑");
  await drawer.getByTestId("open-activity").click();

  await expect(page).toHaveURL(/\/activity\?u=/);
  const act = page.getByTestId("activity");
  await expect(act).toContainText("建了专辑");
  await expect(act.locator(".a-act-row.bad")).toContainText("内容不对，被拒绝");
  await page.getByRole("button", { name: "只看失败" }).click();
  await expect(page.getByTestId("activity-row")).toHaveCount(1);
  await page.getByRole("button", { name: "全部", exact: true }).click();

  const looks = await page.evaluate(async () =>
    (await (await fetch("/api/admin/audit")).json()).rows.filter((r: { action: string }) => r.action === "user.activity").map((r: { target: string }) => r.target),
  );
  expect(looks).toEqual([MEMBER]);
});

test("demo data: merged repeats open up, older activity loads, and it reads in English", async ({ page }) => {
  await signIn(page);
  await page.getByTestId("data-demo").click();
  await page.goto(ADMIN + "/users?u=" + encodeURIComponent("chen.podcast@example.com"));
  await expect(page.getByTestId("drawer-activity")).toBeVisible();
  if (SHOTS) await page.getByTestId("drawer").screenshot({ path: `${SHOTS}/drawer-zh.png` });
  await page.getByTestId("open-activity").click();
  const act = page.getByTestId("activity");
  await expect(act).toContainText("第 12 期：重看《花样年华》");
  const many = act.locator("button.x").first();
  await many.click();
  await expect(act.locator(".each li").first()).toBeVisible();
  await many.click();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/page-zh.png`, fullPage: true });
  await page.getByTestId("activity-older").click();
  await expect(act).toContainText("没有更早的动态了");

  await page.evaluate(() => localStorage.setItem("lacuna.admin.lang", "en"));
  await page.reload();
  await expect(page.getByTestId("activity")).toContainText("Export finished");
  await expect(page.getByRole("button", { name: "Failures only" })).toBeVisible();
  if (SHOTS) {
    await page.screenshot({ path: `${SHOTS}/page-en.png`, fullPage: true });
    await page.evaluate(() => (document.documentElement.dataset.theme = "dark"));
    await page.screenshot({ path: `${SHOTS}/page-en-dark.png`, fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.reload();
    await expect(page.getByTestId("activity")).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/page-en-phone.png`, fullPage: true });
  }
  await page.evaluate(() => localStorage.setItem("lacuna.admin.lang", "zh"));
});
