import { expect, test, type APIRequestContext } from "@playwright/test";

// batch 3 「框架」 on the default server: 申请试用 from the sign-in page reaches the owner by email and lands
// in 设置 → 成员与邀请; the owner invites from there, sets plans; 设置 → 套餐与用量; the show's roles table and
// 「允许 LACUNA 支持查看」 in 节目设置 → 协作者.
const PW = "correct horse battery";
const SHOTS = process.env.PLAN_SHOTS; // folder for review screenshots (optional)

test.describe.configure({ mode: "serial" });
test.beforeAll(async ({ request }) => {
  await request.post("/api/auth/_test/reset?skip_setup=false");
});
test.afterAll(async ({ request }) => {
  await request.post("/api/auth/_test/reset?skip_setup=true");
});

async function mails(request: APIRequestContext, to: string): Promise<{ subject: string; text: string; html?: string }[]> {
  const all = (await (await request.get("/api/auth/_test/outbox")).json()).mails as { to: string; subject: string; text: string; html?: string }[];
  return all.filter((m) => m.to === to);
}

test("申请试用 → the owner's email and list → invite with a plan; 套餐与用量; show roles", async ({ browser, request }) => {
  const leon = await browser.newContext();
  const lp = await leon.newPage();
  expect((await lp.request.post("/api/auth/register", { data: { email: "leon@example.com", password: PW } })).ok()).toBeTruthy();

  // someone without an account asks on the sign-in page
  const guest = await (await browser.newContext()).newPage();
  await guest.goto("/");
  await expect(guest.getByText("从剪辑到发布，一个工作台。")).toBeVisible();
  await guest.getByTestId("auth-ask").click();
  await expect(guest.getByRole("heading", { name: "申请试用" })).toBeVisible();
  await guest.getByTestId("auth-email").fill("ava@example.com");
  await guest.getByTestId("auth-ask-show").fill("夜航电台");
  await guest.getByTestId("auth-ask-note").fill("two hosts, weekly");
  if (SHOTS) await guest.screenshot({ path: `${SHOTS}/ask.png`, fullPage: true });
  await guest.getByRole("button", { name: "提交申请" }).click();
  await expect(guest.getByTestId("auth-asked")).toContainText("ava@example.com");
  const note = (await mails(request, "leon@example.com")).at(-1)!;
  expect(note.subject).toBe("新的试用申请：ava@example.com");
  expect(note.text).toContain("夜航电台");
  expect(note.html).toContain("去发邀请");
  // and the person who asked gets the 「已收到申请」 mail: what happens next, no link
  const got = (await mails(request, "ava@example.com")).at(-1)!;
  expect(got.subject).toBe("我们收到了你的 LACUNA 试用申请");
  expect(got.text).toContain("审核通过后发送邀请");
  expect(got.text).not.toContain("/invite/");

  // the owner's list: invite with one click; the request leaves the list, the invite waits (基础版 by default)
  await lp.goto("/#/settings/members");
  const members = lp.getByRole("region", { name: "成员与邀请" });
  const asks = members.getByTestId("access-requests");
  await expect(asks).toContainText("ava@example.com");
  await expect(asks).toContainText("two hosts, weekly");
  if (SHOTS) await lp.screenshot({ path: `${SHOTS}/requests.png`, fullPage: true });
  await asks.getByRole("button", { name: "发邀请" }).click();
  await expect(members.getByTestId("invite-result")).toContainText("ava@example.com");
  await expect(members.getByTestId("access-requests")).toHaveCount(0);
  await expect(members.getByTestId("invites")).toContainText("基础版");
  expect((await mails(request, "ava@example.com")).at(-1)!.subject).toContain("LACUNA");

  // an invite on the free trial, in the three-section form (对方 / 节目 / 套餐)
  const form = members.getByTestId("invite-form");
  await expect(form).toContainText("邀请邮件发到这个地址");
  await expect(form).toContainText("决定可用时长和节目数");
  await expect(form.getByTestId("invite-plan")).toContainText("基础版 · 每月 4 小时 · 1 个节目");
  await expect(form.getByLabel("在节目里的角色")).toBeDisabled();
  if (SHOTS) await form.screenshot({ path: `${SHOTS}/invite-form.png` });
  await members.getByLabel("对方的邮箱").fill("tia@example.com");
  await members.getByTestId("invite-plan").selectOption("trial");
  await members.getByRole("button", { name: "发送邀请" }).click();
  await expect(members.getByTestId("invite-result")).toContainText("tia@example.com");
  const link = (await members.getByTestId("invite-link").textContent())!;
  await expect(members.getByTestId("invites").locator("li").filter({ hasText: "tia@example.com" })).toContainText("免费体验");

  // the owner's own plan: 专业版, on the house
  await lp.goto("/#/settings/plan");
  await expect(lp.getByTestId("plan-name")).toHaveText("专业版");
  await expect(lp.getByTestId("my-plan")).toContainText("你的套餐由 LACUNA 免费提供。");
  await expect(lp.getByTestId("my-plan")).toContainText("计时稍后开放");
  await expect(lp.getByTestId("plan-table")).toContainText("一次性 1 小时");
  await expect(lp.getByTestId("plan-table")).toContainText("每月 12 小时");
  await expect(lp.getByTestId("plan-table").locator("th.is-mine")).toContainText("专业版");
  if (SHOTS) await lp.screenshot({ path: `${SHOTS}/plan.png`, fullPage: true });

  // Tia signs up from the link: her plan is the trial, with no collaborators
  const tia = await (await browser.newContext()).newPage();
  await tia.goto(link);
  await tia.getByTestId("auth-password").fill(PW);
  await tia.getByTestId("auth-password2").fill(PW);
  await tia.getByRole("button", { name: "创建账号" }).click();
  await expect(tia.locator(".topbar")).toBeVisible();
  await tia.goto("/#/settings/plan");
  await expect(tia.getByTestId("plan-name")).toHaveText("免费体验");
  await expect(tia.getByTestId("plan-table")).toContainText("不能邀请");

  // the owner moves her to 基础版 from the members list
  await lp.goto("/#/settings/members");
  const row = members.getByTestId("members").locator("li").filter({ hasText: "tia@example.com" });
  await row.getByTestId("member-plan").selectOption("basic");
  await expect(row.getByTestId("member-plan")).toHaveValue("basic");
  await tia.reload();
  await expect(tia.getByTestId("plan-name")).toHaveText("基础版");

  // 节目设置 → 协作者: what each role can do, and 「允许 LACUNA 支持查看」 for 7 days
  await lp.goto("/#/project/people");
  await expect(lp.getByTestId("role-matrix")).toContainText("剪辑师");
  const support = lp.getByTestId("support-access");
  await expect(support).toContainText("LACUNA 的工作人员也不行");
  await support.getByTestId("support-toggle").click();
  await expect(support).toContainText("已打开");
  if (SHOTS) await lp.screenshot({ path: `${SHOTS}/support.png`, fullPage: true });
  await support.getByTestId("support-toggle").click();
  await expect(support).toContainText("LACUNA 的工作人员也不行");
  await leon.close();
});
