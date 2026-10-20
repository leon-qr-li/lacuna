import { createHmac } from "node:crypto";
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

async function mails(request: APIRequestContext, to: string): Promise<{ to: string; subject: string; text: string }[]> {
  const all = (await (await request.get("/api/auth/_test/outbox")).json()).mails as { to: string; subject: string; text: string }[];
  return all.filter((m) => m.to === to);
}

async function lastCode(request: APIRequestContext, to: string): Promise<string> {
  const m = (await mails(request, to)).at(-1);
  expect(m, `a mail to ${to}`).toBeTruthy();
  return /\b(\d{6})\b/.exec(m!.text)![1];
}

/** RFC 6238 code for a base32 secret, as an authenticator app shows it (`ahead` steps of 30 s later). */
function totp(secret: string, ahead = 0): string {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const ch of secret.replace(/\s/g, "").toUpperCase()) bits += alphabet.indexOf(ch).toString(2).padStart(5, "0");
  const key = Buffer.from(bits.match(/.{8}/g)!.map((b) => parseInt(b, 2)));
  const msg = Buffer.alloc(8);
  msg.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30_000) + ahead));
  const mac = createHmac("sha1", key).update(msg).digest();
  const off = mac[mac.length - 1] & 15;
  return String((mac.readUInt32BE(off) & 0x7fffffff) % 1_000_000).padStart(6, "0");
}

async function shot(page: Page, name: string) {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true });
}

async function signIn(page: Page, email: string, pw = PW) {
  await page.goto("/");
  await page.getByTestId("auth-email").fill(email);
  await page.getByTestId("auth-password").fill(pw);
  await page.getByRole("button", { name: "登录", exact: true }).click();
}

let recovery: string[] = [];

test("first run: create the owner account, then the app opens", async ({ page }) => {
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

test("设置: owner invites Pei by email; the login page has no open sign-up", async ({ page, request }) => {
  await signIn(page, "leon@example.com", "wrong password!");
  await expect(page.getByRole("alert")).toHaveText("邮箱或密码不对");
  await expect(page.getByText("LACUNA 只对受邀请的人开放。")).toBeVisible();
  await expect(page.getByRole("button", { name: "注册" })).toHaveCount(0);
  await page.getByTestId("auth-password").fill(PW);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.locator(".topbar")).toBeVisible();

  await page.goto("/#/settings");
  const me = page.getByRole("region", { name: "账号与安全" });
  await expect(me.getByTestId("account-email")).toContainText("已登录：leon@example.com");
  await expect(me.getByTestId("account-role")).toHaveText("所有者");
  await expect(me.getByTestId("twostep-state")).toHaveText("没开启");
  await expect(me.getByTestId("devices").getByText("这台设备")).toBeVisible();

  const mail = page.getByRole("region", { name: "邮件" });
  await expect(mail.getByTestId("resend-state")).toContainText("已接上");
  await mail.getByRole("button", { name: "发测试邮件" }).click();
  await expect(mail.getByRole("status")).toHaveText("测试邮件已发到 leon@example.com，去收件箱看看。");

  const members = page.getByRole("region", { name: "成员与邀请" });
  await members.getByLabel("对方的邮箱").fill("pei@example.com");
  await members.getByRole("button", { name: "发送邀请" }).click();
  await expect(members.getByTestId("invite-result")).toContainText("邀请邮件已发到 pei@example.com");
  const link = (await members.getByTestId("invite-link").textContent())!;
  // in the path, not after "#": Cloudflare Access's sign-in on the way in drops a #fragment
  expect(link).toMatch(/[^#]\/invite\/[\w-]{20,}$/);
  const sent = (await mails(request, "pei@example.com")).at(-1)!;
  expect(sent.subject).toBe("leon@example.com 邀请你使用 LACUNA");
  expect(sent.text).toContain(link);
  await expect(members.getByTestId("invites")).toContainText("pei@example.com");
  await shot(page, "settings_members");
  // an English invite email; a fresh browser opens its sign-up page in English
  await expect(members.getByTestId("invite-lang")).toHaveValue("zh");
  await members.getByLabel("对方的邮箱").fill("sam@example.com");
  await members.getByTestId("invite-lang").selectOption("en");
  await members.getByRole("button", { name: "发送邀请" }).click();
  await expect(members.getByTestId("invite-result")).toContainText("邀请邮件已发到 sam@example.com");
  expect((await mails(request, "sam@example.com")).at(-1)!.subject).toBe("leon@example.com invited you to LACUNA");
  const samCtx = await page.context().browser()!.newContext();
  const sam = await samCtx.newPage();
  const samLink = (await members.getByTestId("invite-link").textContent())!;
  await sam.goto(samLink);
  await expect(sam.getByRole("heading", { name: "Accept your invite" })).toBeVisible();
  await samCtx.close();

  // opened where someone is already signed in: say so instead of dropping the invite
  await page.goto(link);
  await expect(page.getByTestId("invite-signed-in")).toContainText("leon@example.com");
  await page.getByRole("button", { name: "继续用 leon@example.com" }).click();
  await expect(page.locator(".topbar")).toBeVisible();
  expect(new URL(page.url()).pathname + new URL(page.url()).hash).toBe("/#/");
  await page.goto("/#/settings");

  // Pei opens the link in another browser
  const pei = await page.context().browser()!.newContext();
  const p = await pei.newPage();
  await p.goto(link);
  await expect(p.getByRole("heading", { name: "接受邀请" })).toBeVisible();
  await expect(p.getByTestId("auth-email")).toHaveValue("pei@example.com");
  await shot(p, "invite");
  await p.getByTestId("auth-password").fill(PW);
  await p.getByTestId("auth-password2").fill(PW);
  await p.getByRole("button", { name: "创建账号" }).click();
  await expect(p.locator(".topbar")).toBeVisible();
  expect(new URL(p.url()).hash).toBe("#/");
  await p.goto("/#/settings");
  await expect(p.getByRole("region", { name: "账号与安全" }).getByTestId("account-role")).toHaveText("成员");
  await expect(p.getByRole("region", { name: "成员与邀请" })).toHaveCount(0); // members don't manage people
  await expect(p.getByRole("region", { name: "邮件" })).toHaveCount(0);
  // Pei, signed in, opens Sam's invite: signing out leads to its sign-up page
  await p.goto(samLink);
  await p.getByRole("button", { name: /退出并接受邀请|Sign out and accept/ }).click();
  await expect(p.getByRole("heading", { name: /接受邀请|Accept your invite/ })).toBeVisible();
  // the link works once
  const again = await (await pei.newPage()).request.post("/api/auth/invite", { data: { token: link.split("/").at(-1) } });
  expect(again.status()).toBe(404);
  await pei.close();

  await page.reload();
  await expect(page.getByRole("region", { name: "成员与邀请" }).getByTestId("members")).toContainText("pei@example.com");
});

test("two-step sign-in: turn it on in 设置, then sign in with the phone code or a recovery code", async ({ page }) => {
  await signIn(page, "leon@example.com");
  await expect(page.locator(".topbar")).toBeVisible();
  await page.getByRole("link", { name: "设置" }).click();
  const me = page.getByRole("region", { name: "账号与安全" });
  await me.getByRole("button", { name: "开启两步验证" }).click();
  await expect(me.getByTestId("twostep-qr")).toBeVisible();
  await me.getByRole("button", { name: "扫不了？手动输入密钥" }).click();
  const secret = (await me.getByTestId("twostep-secret").textContent())!;
  await me.getByTestId("auth-code").fill(totp(secret));
  await shot(page, "settings_twostep");
  await me.getByRole("button", { name: "确认开启" }).click();
  await expect(me.getByTestId("recovery-codes").locator("li")).toHaveCount(10);
  recovery = await me.getByTestId("recovery-codes").locator("li").allTextContents();
  await expect(me.getByRole("button", { name: "完成" })).toBeDisabled();
  await me.getByTestId("recovery-saved").check();
  await me.getByRole("button", { name: "完成" }).click();
  await expect(me.getByTestId("twostep-state")).toHaveText("已开启");

  await me.getByRole("button", { name: "退出登录" }).click();
  await signIn(page, "leon@example.com");
  await expect(page.getByRole("heading", { name: "两步验证" })).toBeVisible();
  await shot(page, "login_twostep");
  await page.getByTestId("auth-code").fill(totp(secret) === "000000" ? "111111" : "000000");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByRole("alert")).toHaveText("两步验证码不对");
  await page.getByRole("button", { name: "手机不在身边？用恢复码" }).click();
  await page.getByTestId("auth-recovery").fill(recovery[0]);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.locator(".topbar")).toBeVisible();
});

test("forgot password: email code, new password, then the two-step code", async ({ page, request }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "忘记密码？" }).click();
  await expect(page.getByRole("heading", { name: "重设密码" })).toBeVisible();
  await page.getByTestId("auth-email").fill("leon@example.com");
  await page.getByRole("button", { name: "发送验证码" }).click();
  await expect(page.getByText("已发送到 leon@example.com（没有这个账号就不会收到）")).toBeVisible();
  const code = await lastCode(request, "leon@example.com");
  await page.getByTestId("auth-code").fill(code === "000000" ? "111111" : "000000");
  await page.getByTestId("auth-password").fill("a brand new password");
  await page.getByRole("button", { name: "保存并登录" }).click();
  await expect(page.getByRole("alert")).toHaveText("验证码不对");
  await page.getByTestId("auth-code").fill(code);
  await page.getByRole("button", { name: "保存并登录" }).click();
  await expect(page.getByRole("heading", { name: "两步验证" })).toBeVisible();
  // not changed until the second step passes
  expect((await request.post("/api/auth/login", { data: { email: "leon@example.com", password: "a brand new password" } })).status()).toBe(401);
  await page.getByRole("button", { name: "手机不在身边？用恢复码" }).click();
  await page.getByTestId("auth-recovery").fill(recovery[1]);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.locator(".topbar")).toBeVisible();
  expect((await request.post("/api/auth/login", { data: { email: "leon@example.com", password: PW } })).status()).toBe(401);
});

test("cloud: the first sign-in sets up two-step before the app opens", async ({ page, request }) => {
  await request.post("/api/auth/_test/reset?skip_setup=false&cloud=true");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "创建你的账号" })).toBeVisible();
  await expect(page.getByText("这是 LACUNA 的第一个账号，也就是所有者：之后由你邀请别人。")).toBeVisible();
  await page.getByTestId("auth-email").fill("leon@example.com");
  await page.getByTestId("auth-password").fill(PW);
  await page.getByTestId("auth-password2").fill(PW);
  await page.getByRole("button", { name: "创建账号" }).click();
  await expect(page.getByRole("heading", { name: "设置两步验证" })).toBeVisible();
  expect((await page.request.get("/api/episodes")).status()).toBe(401); // no session before the code
  await shot(page, "cloud_enroll");
  await page.getByRole("button", { name: "扫不了？手动输入密钥" }).click();
  const secret = (await page.getByTestId("twostep-secret").textContent())!;
  await page.getByTestId("auth-code").fill(totp(secret));
  await page.getByRole("button", { name: "确认并继续" }).click();
  await expect(page.getByRole("heading", { name: "保存恢复码" })).toBeVisible();
  await expect(page.getByTestId("recovery-codes").locator("li")).toHaveCount(10);
  await shot(page, "cloud_recovery");
  await page.getByTestId("recovery-saved").check();
  await page.getByRole("button", { name: "进入 LACUNA" }).click();
  await expect(page.locator(".topbar")).toBeVisible();
  await page.goto("/#/settings");
  const me = page.getByRole("region", { name: "账号与安全" });
  await expect(me.getByTestId("twostep-state")).toHaveText("已开启");
  await expect(me.getByRole("button", { name: "关闭" })).toHaveCount(0); // required online
});

test("the API refuses calls without a session", async ({ request }) => {
  const r = await request.get("/api/episodes");
  expect(r.status()).toBe(401);
  expect((await request.get("/api/health")).status()).toBe(200);
});
