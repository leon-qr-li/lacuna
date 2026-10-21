import { expect, test, type Browser } from "@playwright/test";

// projects (decision projects-albums) on the default server: an invited beta user starts in an empty
// project of their own; Leon brings them into his project as a listener with 邀请协作; with two projects
// they land on 所有项目, open Leon's, and can listen but not change. They can also start a project.
const PW = "correct horse battery";
const SHOTS = process.env.PROJECT_SHOTS; // folder for review screenshots (optional)

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

test("beta user sees only their own project until invited to Leon's", async ({ browser }) => {
  const leon = await browser.newContext();
  const lp = await leon.newPage();
  expect((await lp.request.post("/api/auth/register", { data: { email: "leon@example.com", password: PW } })).ok()).toBeTruthy();
  const inv = await (await lp.request.post("/api/auth/invites", { data: { email: "beta@example.com" } })).json();
  const b = await (await browser.newContext()).newPage();
  expect((await b.request.post("/api/auth/register", { data: { invite: inv.link.split("/").at(-1), password: PW } })).ok()).toBeTruthy();

  const beta = await browserAs(browser, "beta@example.com");
  await expect(beta.getByText("合成测试集")).toHaveCount(0); // Leon's episode is not theirs
  await expect(beta.getByTestId("show-setup")).toContainText("建你的第一个节目");
  await expect(beta.getByTestId("invite-link")).toBeVisible(); // they manage their own project

  // Leon invites them from the top bar's 邀请协作, as a listener; they have an account, so they join at once
  await lp.goto("/#/");
  await lp.getByTestId("invite-link").click();
  await expect(lp.getByRole("heading", { name: /邀请协作「洛城二三事」/ })).toBeVisible();
  await lp.getByTestId("invite-email").fill("beta@example.com");
  await lp.getByTestId("invite-role").selectOption({ label: "只听" });
  await lp.getByTestId("invite-send").click();
  await expect(lp.getByText("beta@example.com 已经加进来了")).toBeVisible();
  const row = lp.getByTestId("collaborator").filter({ hasText: "beta@example.com" });
  await expect(row.getByRole("combobox")).toHaveValue("viewer");
  // someone without an account: Leon (LACUNA's owner) sends a sign-up invite that waits as 待接受
  await lp.getByTestId("invite-email").fill("pei@example.com");
  await lp.getByTestId("invite-role").selectOption({ label: "剪辑" });
  await lp.getByTestId("invite-send").click();
  const pending = lp.getByTestId("pending-invite").filter({ hasText: "pei@example.com" });
  await expect(pending).toContainText("剪辑 · 待接受");
  await pending.getByRole("button", { name: "撤回" }).click();
  if (SHOTS) await lp.screenshot({ path: `${SHOTS}/invite.png`, fullPage: true });
  await expect(lp.getByTestId("pending-invite")).toHaveCount(0);

  // with two projects the beta user lands on 所有项目 and opens Leon's
  const fresh = await browserAs(browser, "beta@example.com");
  await expect(fresh).toHaveURL(/#\/projects$/);
  const card = fresh.getByTestId("project-card").filter({ hasText: "洛城二三事" });
  await expect(card).toContainText("leon@example.com 邀请你 · 只听");
  if (SHOTS) await fresh.screenshot({ path: `${SHOTS}/projects.png`, fullPage: true });
  await card.click();
  await expect(fresh.getByText("合成测试集")).toBeVisible();
  await expect(fresh.getByTestId("project-menu")).toHaveText(/洛城二三事/);
  await expect(fresh.getByTestId("invite-link")).toHaveCount(0); // not a manager here
  const r = await fresh.request.post("/api/episodes/EP_TEST_合成/undo");
  expect(r.status()).toBe(403);

  // the project menu switches back, and starts a new project
  await fresh.getByTestId("project-menu").click();
  if (SHOTS) await fresh.screenshot({ path: `${SHOTS}/menu.png` });
  await fresh.getByTestId("project-new").click();
  // the dialog sits in the middle of the window, not stuck against the top bar
  const box = (await fresh.getByTestId("project-new-dialog").boundingBox())!;
  const vp = fresh.viewportSize()!;
  expect(box.y).toBeGreaterThan(40);
  expect(Math.abs(box.y + box.height / 2 - vp.height / 2)).toBeLessThan(40);
  expect(Math.abs(box.x + box.width / 2 - vp.width / 2)).toBeLessThan(40);
  await fresh.getByTestId("project-name").fill("片场夜谈");
  await fresh.getByTestId("project-create").click();
  await expect(fresh.getByTestId("project-menu")).toHaveText(/片场夜谈/);
  await expect(fresh.getByTestId("show-setup")).toContainText("介绍一下「片场夜谈」");
  await leon.close();
});
