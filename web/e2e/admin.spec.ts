// The admin site (decision 2026-10-24-admin-site) on admin.localhost: sign-in with password + code, the inbox
// (feedback text shown as text, reply reaches the person), the step-up code before a dangerous change, demo
// data that saves nothing, English, and the main address never answering /api/admin.
import { expect, test, type Page } from "@playwright/test";

const ADMIN = "http://admin.localhost:8799";
const OWNER = "leon@example.com";
const MEMBER = "pei@example.com";
const PW = "correct horse battery";

test.beforeEach(async ({ request, page }) => {
  await request.post("/api/auth/_test/reset?skip_setup=false");
  await page.goto(ADMIN + "/");
  const seeded = await page.evaluate(async () => (await fetch("/api/admin/_test/seed", { method: "POST", headers: { "X-Lacuna-Admin": "1" } })).status);
  expect(seeded).toBe(200);
});

test.afterEach(async ({ request }) => {
  await request.post("/api/auth/_test/reset?skip_setup=true");
});

async function code(page: Page, email = OWNER): Promise<string> {
  return page.evaluate(async (e) => (await (await fetch(`/api/admin/_test/code?email=${encodeURIComponent(e)}`)).json()).code, email);
}

async function signIn(page: Page) {
  await page.goto(ADMIN + "/");
  await page.getByTestId("login-email").fill(OWNER);
  await page.getByTestId("login-password").fill(PW);
  await page.getByTestId("login-code").fill(await code(page));
  await page.getByTestId("login-submit").click();
  await expect(page.getByTestId("todo")).toBeVisible();
}

test("the main address has no admin; the admin asks for password and code", async ({ page, request }) => {
  expect((await request.get("/api/admin/overview")).status()).toBe(404);
  await page.goto(ADMIN + "/");
  await page.getByTestId("login-email").fill(OWNER);
  await page.getByTestId("login-password").fill(PW);
  await page.getByTestId("login-code").fill("000000");
  await page.getByTestId("login-submit").click();
  await expect(page.getByTestId("login-error")).toBeVisible();
  await expect(page.getByTestId("todo")).toHaveCount(0);
  // a member never gets in, with a correct password and no matter what code
  await page.getByTestId("login-email").fill(MEMBER);
  await page.getByTestId("login-code").fill("123456");
  await page.getByTestId("login-submit").click();
  await expect(page.getByTestId("login-error")).toBeVisible();
});

test("feedback: shown as text, replied to, and the reply reaches the person", async ({ page }) => {
  await signIn(page);
  await page.goto(ADMIN + "/feedback");
  await page.getByTestId("fb-item").first().click();
  // the HTML in the feedback is shown as characters, never run
  await expect(page.getByTestId("fb-text")).toContainText("<b>导出按钮</b>");
  await expect(page.getByTestId("fb-text").locator("b")).toHaveCount(0);
  await page.getByTestId("fb-reply-text").fill("谢谢，下个版本修好");
  await page.getByTestId("fb-reply").click();
  await expect(page.getByTestId("fb-detail")).toContainText("谢谢，下个版本修好");
  const log = await page.evaluate(async () => (await (await fetch("/api/admin/audit")).json()).rows.map((r: { action: string }) => r.action));
  expect(log).toContain("feedback.reply");
});

test("a dangerous change asks for the code again", async ({ page }) => {
  await signIn(page);
  await page.goto(ADMIN + "/users");
  await page.getByTestId("user-row").filter({ hasText: MEMBER }).click();
  await expect(page.getByTestId("drawer")).toBeVisible();
  await page.getByTestId("user-plan").selectOption("pro");
  await expect(page.getByTestId("stepup")).toBeVisible();
  await page.getByTestId("stepup-code").fill(await code(page));
  await page.getByTestId("stepup-ok").click();
  await expect(page.getByTestId("stepup")).toHaveCount(0);
  await expect(page.getByTestId("user-plan")).toHaveValue("pro");
  const plan = await page.evaluate(async (e) => (await (await fetch(`/api/admin/users/${e}`)).json()).user.plan, MEMBER);
  expect(plan).toBe("pro");
});

test("demo data saves nothing, and the admin speaks English", async ({ page }) => {
  await signIn(page);
  await page.getByTestId("data-demo").click();
  await expect(page.locator(".a-demo-bar")).toBeVisible();
  await page.goto(ADMIN + "/feedback");
  await page.getByTestId("fb-item").first().click();
  await page.getByTestId("fb-reply-text").fill("演示里的回复");
  await page.getByTestId("fb-reply").click();
  await expect(page.getByTestId("toast")).toBeVisible();
  const replies = await page.evaluate(async () => (await (await fetch("/api/admin/feedback")).json()).items.flatMap((i: { replies?: { text: string }[] }) => i.replies ?? []));
  expect(replies.map((r: { text: string }) => r.text)).not.toContain("演示里的回复");
  await page.getByTestId("data-real").click();
  await page.getByTestId("lang-en").click();
  await page.goto(ADMIN + "/");
  await expect(page.getByTestId("todo")).toContainText("To do");
  await expect(page.locator("body")).not.toContainText(/Claude|Anthropic/);
});

test("main site: the notice bar and maintenance set in the admin; 想要更多时长 reaches the admin", async ({ page, browser }) => {
  await signIn(page);
  const put = (url: string, body: object) =>
    page.evaluate(async ([u, b]) => (await fetch(u as string, { method: "PUT", headers: { "Content-Type": "application/json", "X-Lacuna-Admin": "1" }, body: JSON.stringify(b) })).status, [url, body] as const);
  expect(await put("/api/admin/settings/notice", { on: true, zh: "今晚 10 点升级", en: "Upgrade at 10 pm", until: null })).toBe(200);

  const pei = await (await browser.newContext()).newPage();
  expect((await pei.request.post("/api/auth/login", { data: { email: MEMBER, password: PW } })).ok()).toBeTruthy();
  await pei.goto("/#/settings/plan");
  await expect(pei.getByTestId("site-notice")).toContainText("今晚 10 点升级");
  await pei.getByTestId("site-notice").getByRole("button").click();
  await expect(pei.getByTestId("site-notice")).toHaveCount(0);

  await pei.getByTestId("more-hours-open").click();
  await pei.getByTestId("more-hours-n").fill("3");
  await pei.getByTestId("more-hours-reason").fill("这个月有两集长访谈");
  await pei.getByTestId("more-hours-send").click();
  await expect(pei.getByTestId("more-hours-open")).toBeDisabled();

  await page.goto(ADMIN + "/hours");
  await expect(page.getByText("这个月有两集长访谈")).toBeVisible();

  // maintenance: the owner turns it on (with the code again); the main site says so and refuses new imports
  const r = await page.evaluate(async () => (await fetch("/api/admin/settings/maintenance", { method: "PUT", headers: { "Content-Type": "application/json", "X-Lacuna-Admin": "1" }, body: JSON.stringify({ on: true }) })).status);
  expect(r).toBe(403);
  const c = await code(page);
  expect(await page.evaluate(async (x) => (await fetch("/api/admin/auth/stepup", { method: "POST", headers: { "Content-Type": "application/json", "X-Lacuna-Admin": "1" }, body: JSON.stringify({ code: x }) })).status, c)).toBe(200);
  expect(await put("/api/admin/settings/maintenance", { on: true })).toBe(200);
  await pei.reload();
  await expect(pei.getByTestId("site-notice")).toContainText("正在维护");
  expect((await pei.request.post("/api/imports", { data: {} })).status()).toBe(503);
  expect(await put("/api/admin/settings/maintenance", { on: false })).toBe(200);
});
