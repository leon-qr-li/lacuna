import { expect, test } from "@playwright/test";

// 用户条款和隐私政策 (decision 2026-10-25-terms-and-privacy): the two pages open without signing in, the sign-in
// screen links to them, and in the cloud an account that hasn't agreed to the current version agrees before the app.
const PW = "correct horse battery";

test.describe.configure({ mode: "serial" });
test.beforeAll(async ({ request }) => {
  await request.post("/api/auth/_test/reset?skip_setup=false");
});
test.afterAll(async ({ request }) => {
  await request.post("/api/auth/_test/reset?skip_setup=true");
});

test("the terms and the privacy policy open without signing in, in both languages", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "创建你的账号" })).toBeVisible();
  const terms = page.getByTestId("auth-legal").getByTestId("legal-link-terms");
  await expect(terms).toHaveAttribute("href", "/legal/terms");
  await expect(terms).toHaveAttribute("target", "_blank");

  await page.goto("/legal/terms");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("LACUNA 用户条款");
  await expect(page.getByText("请只上传你有权使用的音乐。")).toBeVisible();
  await expect(page.getByRole("heading", { name: "7. 版权投诉（DMCA）" })).toBeVisible();
  await expect(page.locator(".legal-tbd").first()).toContainText("待定"); // what the lawyer's version fills in
  await page.getByRole("link", { name: "隐私政策" }).click();
  await expect(page).toHaveURL(/\/legal\/privacy$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("LACUNA 隐私政策");
  await expect(page.getByText("从不发给任何 AI 服务").first()).toBeVisible();

  await page.getByRole("button", { name: "English" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("LACUNA Privacy Policy");
  await expect(page.getByRole("link", { name: "Terms of Service" })).toBeVisible();
  await page.getByRole("button", { name: "中文" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("LACUNA 隐私政策");
});

test("in the cloud, an account that hasn't agreed yet agrees before the app opens", async ({ page }) => {
  expect((await page.request.post("/api/auth/register", { data: { email: "leon@example.com", password: PW, name: "Leon" } })).ok()).toBeTruthy();
  // the cloud server's answer (this E2E server is a checkout, where agreeing is optional)
  await page.route("**/api/auth/status", async (route) => {
    const res = await route.fetch();
    await route.fulfill({ response: res, json: { ...(await res.json()), cloud: true } });
  });
  await page.goto("/#/");
  const gate = page.getByTestId("legal-consent");
  await expect(gate.getByRole("heading", { name: "请确认用户条款和隐私政策" })).toBeVisible();
  await expect(page.locator(".topbar")).toHaveCount(0);
  await gate.getByTestId("legal-continue").click();
  await expect(gate.getByRole("alert")).toHaveText("请先勾选同意用户条款和隐私政策");
  await gate.getByTestId("legal-agree").check();
  await gate.getByTestId("legal-continue").click();
  await expect(page.locator(".topbar")).toBeVisible();
  await page.goto("/#/settings/account");
  await expect(page.getByTestId("account-legal")).toContainText("你同意的版本");
  await page.reload();
  await expect(page.locator(".topbar")).toBeVisible(); // agreed once: not asked again
});
