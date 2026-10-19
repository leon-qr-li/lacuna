import { expect, test, type Browser } from "@playwright/test";

// workspaces on the default server: an invited beta user gets an empty private workspace; Leon adds them
// to his workspace as a listener, they switch with the top-bar menu and can listen but not change.
const PW = "correct horse battery";

test.describe.configure({ mode: "serial" });
test.beforeAll(async ({ request }) => {
  await request.post("/api/auth/_test/reset?skip_setup=false");
});
test.afterAll(async ({ request }) => {
  await request.post("/api/auth/_test/reset?skip_setup=true");
});

async function browserAs(browser: Browser, email: string) {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.goto("/");
  await page.getByTestId("auth-email").fill(email);
  await page.getByTestId("auth-password").fill(PW);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.locator(".topbar")).toBeVisible();
  return page;
}

test("beta user sees only their own workspace until added to Leon's", async ({ browser }) => {
  // Leon's account (the first one) and an invite with a workspace of their own (the default)
  const leon = await browser.newContext();
  const lp = await leon.newPage();
  expect((await lp.request.post("/api/auth/register", { data: { email: "leon@example.com", password: PW } })).ok()).toBeTruthy();
  const inv = await (await lp.request.post("/api/auth/invites", { data: { email: "beta@example.com" } })).json();
  const b = await (await browser.newContext()).newPage();
  expect((await b.request.post("/api/auth/register", { data: { invite: inv.link.split("/").at(-1), password: PW } })).ok()).toBeTruthy();

  const beta = await browserAs(browser, "beta@example.com");
  await expect(beta.getByText("合成测试集")).toHaveCount(0); // Leon's episode is not theirs
  await expect(beta.getByTestId("space-switch")).toHaveCount(0); // one workspace: no menu

  // Leon adds them to his workspace as a listener, in 设置 → 工作区
  await lp.goto("/#/settings");
  const card = lp.getByRole("region", { name: "工作区" });
  await expect(card.getByTestId("space-current")).toContainText("（管理）");
  const main = card.getByTestId("space-main");
  await main.getByLabel("加成员的邮箱").fill("beta@example.com");
  await main.getByLabel("角色", { exact: true }).selectOption({ label: "只听" });
  await main.getByRole("button", { name: "加进来" }).click();
  await expect(main.getByText("beta@example.com")).toBeVisible();

  // the beta user switches to it from the top bar and can listen, not change
  await beta.reload();
  const menu = beta.getByTestId("space-switch");
  await expect(menu).toBeVisible();
  await menu.selectOption({ label: "leon" });
  await expect(beta.getByText("合成测试集")).toBeVisible();
  const r = await beta.request.post("/api/episodes/EP_TEST_合成/undo");
  expect(r.status()).toBe(403);
  await beta.getByRole("link", { name: "设置" }).click();
  await expect(beta.getByRole("region", { name: "工作区" }).getByTestId("space-current")).toContainText("（只听）");
  await leon.close();
});
