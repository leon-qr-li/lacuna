import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// default server (playwright.config.ts) with a fake mailer (tests/app/e2e/auth.py). The other specs run
// without accounts, so this one switches the first-account screen on and leaves the server as it found it.
const PW = "correct horse battery";
const SHOTS = process.env.AUTH_SHOTS; // folder for review screenshots (optional)

test.describe.configure({ mode: "serial" });
test.beforeAll(async ({ request }) => {
  await request.post("/api/auth/_test/reset?skip_setup=false");
});
test.afterAll(async ({ request }) => {
  await request.post("/api/auth/_test/reset?skip_setup=true");
});

async function lastCode(request: APIRequestContext, to: string): Promise<string> {
  const mails = (await (await request.get("/api/auth/_test/outbox")).json()).mails as { to: string; text: string }[];
  const m = [...mails].reverse().find((x) => x.to === to);
  expect(m, `a mail to ${to}`).toBeTruthy();
  return /\b(\d{6})\b/.exec(m!.text)![1];
}

async function shot(page: Page, name: string) {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png` });
}

test("first run: create the owner account (no code), then the app opens", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "创建你的账号" })).toBeVisible();
  await expect(page.getByText("Mind the gaps. Keep the voice.")).toBeVisible();
  await shot(page, "first_run");
  await page.getByTestId("auth-email").fill("leon@example.com");
  await page.getByTestId("auth-password").fill("short");
  await expect(page.getByText("密码强度：太短")).toBeVisible();
  await page.getByTestId("auth-password2").fill("short");
  await page.getByRole("button", { name: "创建账号" }).click();
  await expect(page.getByRole("alert")).toHaveText("密码至少要 10 位");
  await page.getByTestId("auth-password").fill(PW);
  await page.getByTestId("auth-password2").fill(PW + "x");
  await page.getByRole("button", { name: "创建账号" }).click();
  await expect(page.getByRole("alert")).toHaveText("两次输入的密码不一样");
  await page.getByTestId("auth-password2").fill(PW);
  await page.getByRole("button", { name: "创建账号" }).click();
  await expect(page.getByRole("heading", { name: "创建你的账号" })).toBeHidden();
  await expect(page.locator(".topbar")).toBeVisible();
});

test("设置 → 账号与邮件: test email, open sign-up, sign out, sign in again", async ({ page, request }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "欢迎回来" })).toBeVisible();   // a new browser context: no session
  await shot(page, "login");
  await page.getByTestId("auth-email").fill("leon@example.com");
  await page.getByTestId("auth-password").fill("wrong password!");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByRole("alert")).toHaveText("邮箱或密码不对");
  await page.getByTestId("auth-password").fill(PW);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.locator(".topbar")).toBeVisible();

  await page.goto("/#/settings");
  const card = page.getByRole("region", { name: "账号与邮件" });
  await expect(card.getByTestId("account-email")).toHaveText("已登录：leon@example.com");
  await expect(card.getByTestId("resend-state")).toContainText("已接上");
  await card.getByRole("button", { name: "发测试邮件" }).click();
  await expect(card.getByRole("status")).toHaveText("测试邮件已发到 leon@example.com，去收件箱看看。");
  const mails = (await (await request.get("/api/auth/_test/outbox")).json()).mails;
  expect(mails.at(-1).subject).toBe("LACUNA 测试邮件");
  await card.getByTestId("allow-register").click({ force: true }); // controlled: flips once the server answers
  await expect(card.getByTestId("allow-register")).toBeChecked();
  await shot(page, "settings_account");

  await card.getByRole("button", { name: "退出登录" }).click();
  await expect(page.getByRole("heading", { name: "欢迎回来" })).toBeVisible();
  await expect(page.getByRole("button", { name: "注册" })).toBeVisible();      // sign-up is open now

  // signing in again lands on 剧集, not back on 设置 where the sign-out happened
  await page.getByTestId("auth-email").fill("leon@example.com");
  await page.getByTestId("auth-password").fill(PW);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1, name: "剧集" })).toBeVisible();
  expect(new URL(page.url()).hash).toBe("#/");
  await page.goto("/#/settings");
  await page.getByRole("region", { name: "账号与邮件" }).getByRole("button", { name: "退出登录" }).click();
  await expect(page.getByRole("heading", { name: "欢迎回来" })).toBeVisible();
});

test("a second account needs an email code", async ({ page, request }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "注册" }).click();
  await expect(page.getByRole("heading", { name: "创建账号" })).toBeVisible();
  await page.getByTestId("auth-email").fill("pei@example.com");
  await page.getByTestId("auth-password").fill(PW);
  await page.getByTestId("auth-password2").fill(PW);
  await page.getByRole("button", { name: "创建账号" }).click();
  await expect(page.getByRole("alert")).toHaveText("先发验证码，再填邮件里的 6 位数字");
  await page.getByRole("button", { name: "发送验证码" }).click();
  await expect(page.getByText("已发送到 pei@example.com")).toBeVisible();
  await expect(page.getByRole("button", { name: /重新发送（\d+s）/ })).toBeDisabled();
  await page.getByTestId("auth-code").fill(await lastCode(request, "pei@example.com"));
  await shot(page, "register_code");
  await page.getByRole("button", { name: "创建账号" }).click();
  await expect(page.locator(".topbar")).toBeVisible();
});

test("forgot password: code by email, new password, signed in", async ({ page, request }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "忘记密码？" }).click();
  await expect(page.getByRole("heading", { name: "重设密码" })).toBeVisible();
  await page.getByTestId("auth-email").fill("leon@example.com");
  await page.getByRole("button", { name: "发送验证码" }).click();
  await expect(page.getByText("已发送到 leon@example.com（没有这个账号就不会收到）")).toBeVisible();
  await page.getByTestId("auth-code").fill("000000" === (await lastCode(request, "leon@example.com")) ? "111111" : "000000");
  await page.getByTestId("auth-password").fill("a brand new password");
  await page.getByRole("button", { name: "保存并登录" }).click();
  await expect(page.getByRole("alert")).toHaveText("验证码不对");
  await page.getByTestId("auth-code").fill(await lastCode(request, "leon@example.com"));
  await shot(page, "forgot_code");
  await page.getByRole("button", { name: "保存并登录" }).click();
  await expect(page.locator(".topbar")).toBeVisible();

  // the old password is gone
  const r = await request.post("/api/auth/login", { data: { email: "leon@example.com", password: PW } });
  expect(r.status()).toBe(401);
});

test("the API refuses calls without a session", async ({ request }) => {
  const r = await request.get("/api/episodes");
  expect(r.status()).toBe(401);
  expect((await request.get("/api/health")).status()).toBe(200);
});
