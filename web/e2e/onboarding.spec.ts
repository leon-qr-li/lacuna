import { expect, test } from "@playwright/test";

// 入门 (new-user batch): a new person signs up from an invite with their name → 欢迎，Sam with the plan line →
// LACUNA 示例节目 with the coach (A/B, keep, reset) → back to their own show → 建节目 → 入门清单 and
// 节目资料卡 → 设置 → 通用 deletes the sample. Progress is the server's, per person.
const PW = "correct horse battery";

test.describe.configure({ mode: "serial" });
test.beforeAll(async ({ request }) => {
  await request.post("/api/auth/_test/reset?skip_setup=false");
});
test.afterAll(async ({ request }) => {
  await request.post("/api/auth/_test/reset?skip_setup=true");
});

test("welcome → sample show with the coach → own show → checklist", async ({ browser }) => {
  const leon = await (await browser.newContext()).newPage();
  expect((await leon.request.post("/api/auth/register", { data: { email: "leon@example.com", password: PW, name: "Leon" } })).ok()).toBeTruthy();
  const inv = await (await leon.request.post("/api/auth/invites", { data: { email: "sam@example.com", plan: "basic" } })).json();
  // Leon has episodes: no guide for him
  await leon.goto("/#/");
  await expect(leon.getByTestId("home-hero").or(leon.locator(".home-hero"))).toBeVisible();
  await expect(leon.getByTestId("welcome")).toHaveCount(0);
  await expect(leon.getByTestId("onboard-card")).toHaveCount(0);

  const sam = await (await browser.newContext()).newPage();
  await sam.goto(inv.link);
  await expect(sam.getByText("Leon 邀请你")).toBeVisible();
  await sam.getByTestId("auth-name").fill("Sam");
  await sam.getByTestId("auth-password").fill(PW);
  await sam.getByTestId("auth-password2").fill(PW);
  await sam.getByRole("button", { name: "创建账号" }).click();
  const welcome = sam.getByTestId("welcome");
  await expect(welcome.getByRole("heading", { level: 1 })).toHaveText("欢迎，Sam");
  await expect(sam.getByTestId("welcome-plan")).toContainText("基础版 · 每月 4 小时音频");
  await expect(sam.getByTestId("show-setup")).toHaveCount(0);

  // the sample: straight into its review, the coach at step 1
  await sam.getByTestId("welcome-sample").click();
  await expect(sam).toHaveURL(/#\/ep\/SAMPLE_01\/review/);
  const coach = sam.getByTestId("coach");
  await expect(coach).toContainText("0/5");
  await expect(coach.locator("li.is-next")).toContainText("听一处删减");
  await expect(sam.getByTestId("review-title")).toBeVisible();
  await sam.getByRole("button", { name: "A · 原话" }).click();
  await expect(coach.locator("li.is-next")).toContainText("保留或恢复");
  await sam.keyboard.press("k");
  await expect(coach).toContainText("2/5");
  await expect(coach.locator("li.is-next")).toContainText("整集试听");
  // the coach's ticks follow Sam to another browser
  const again = await (await browser.newContext()).newPage();
  await again.request.post("/api/auth/login", { data: { email: "sam@example.com", password: PW } });
  const ob = await (await again.request.get("/api/onboarding")).json();
  expect(ob.done).toEqual(expect.arrayContaining(["sample.ab", "sample.decide"]));
  // 重置示例: the first cut as it was, the coach from the start
  await coach.getByTestId("coach-reset").click();
  await sam.getByRole("dialog").getByRole("button", { name: "重置示例" }).click();
  await expect(sam.getByTestId("coach")).toContainText("0/5");

  // their own show: the welcome again until it is set up; 建我的节目 opens the form
  await sam.getByTestId("coach-own").click();
  await expect(sam.getByTestId("welcome")).toBeVisible();
  await sam.getByTestId("welcome-own").click();
  const setup = sam.getByTestId("show-setup");
  await setup.getByTestId("show-name").fill("Late Night Reel");
  await setup.getByLabel("第 1 位主持人的名字").fill("Sam");
  await setup.getByTestId("show-save").click();
  const card = sam.getByTestId("onboard-card");
  await expect(card.getByTestId("onboard-progress")).toHaveText("1/6");
  await expect(card.locator("li.is-next")).toContainText("导入第一集");
  // 节目资料卡: the description filled in place
  const profile = sam.getByTestId("profile-card");
  await profile.getByTestId("profile-about").click();
  await profile.getByTestId("profile-about-input").fill("两位主持人聊刚看过的电影");
  await profile.getByRole("button", { name: "保存" }).click();
  await expect(profile.locator("li.is-done")).toContainText("两位主持人聊刚看过的电影");
  await profile.getByTestId("profile-off").click();
  await expect(sam.getByTestId("profile-card")).toHaveCount(0);
  // the sample isn't one of the plan's shows (基础版: 1)
  await sam.goto("/#/settings/plan");
  await expect(sam.getByTestId("plan-shows")).toContainText("1");
  // hidden, and brought back from 设置 → 通用; the sample deleted there too
  await sam.goto("/#/");
  await sam.getByTestId("onboard-hide").click();
  await expect(sam.getByTestId("onboard-card")).toHaveCount(0);
  await sam.goto("/#/settings/general");
  const st = sam.getByTestId("onboard-settings");
  await st.getByTestId("onboard-show").click();
  await st.getByTestId("sample-drop").click();
  await sam.getByRole("dialog").getByRole("button", { name: "删除" }).click();
  await expect(st.getByTestId("sample-open")).toHaveText("添加示例节目");
  await sam.goto("/#/");
  await expect(sam.getByTestId("onboard-card")).toBeVisible();
});
