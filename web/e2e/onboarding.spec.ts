import { expect, test } from "@playwright/test";

// 入门 (new-user batch): a new person signs up from an invite with their name → 欢迎，Sam with the plan line →
// LACUNA 示例节目 with the bubble tour (resume elsewhere, leave, restart, the end) → back to their own show → 建节目 → 入门清单 and
// 节目资料卡 → 设置 → 通用 deletes the sample. Progress is the server's, per person.
const PW = "correct horse battery";

test.describe.configure({ mode: "serial" });
test.beforeAll(async ({ request }) => {
  await request.post("/api/auth/_test/reset?skip_setup=false");
});
test.afterAll(async ({ request }) => {
  await request.post("/api/auth/_test/reset?skip_setup=true");
});

test("welcome → sample show with the tour → own show → checklist", async ({ browser }) => {
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

  // the sample: straight into its review, the bubble tour at its first step (the raw recording)
  await sam.getByTestId("welcome-sample").click();
  await expect(sam).toHaveURL(/#\/ep\/SAMPLE_01\/review/);
  await expect(sam.getByTestId("tour-pill")).toContainText("第 1 步，共 7 步");
  await expect(sam.getByTestId("tour-raw")).toContainText("先听听没剪过的样子");
  // no 知道了 here: play is the only control; paused from the pill → on to the next step
  await expect(sam.getByTestId("tour-raw").getByTestId("tour-ok")).toHaveCount(0);
  await sam.getByTestId("tour-raw-play").click();
  await expect.poll(() => sam.getByTestId("tour-raw-audio").evaluate((a: HTMLAudioElement) => a.currentTime)).toBeGreaterThan(0.1);
  await sam.getByTestId("tour-pause").click();
  const bubble = sam.getByTestId("tour-bubble");
  await expect(bubble).toContainText("LACUNA 拿不准的 3 处");
  await expect(bubble).toContainText("审阅改动 · 1/3");
  await bubble.getByTestId("tour-ok").click();
  await expect(bubble).toContainText("先听，再决定");
  await bubble.getByTestId("tour-ok").click(); // LACUNA plays A, then B, then goes on
  await expect(bubble).toContainText("保留，还是恢复？", { timeout: 60_000 });
  // the place reached follows Sam to another browser
  const again = await (await browser.newContext()).newPage();
  await again.request.post("/api/auth/login", { data: { email: "sam@example.com", password: PW } });
  await expect.poll(async () => (await (await again.request.get("/api/onboarding")).json()).tour).toBe("rdecide");
  // the one way out is the quiet × on the pill; it asks first (继续教程 stays), then remembers the step
  await expect(bubble.getByRole("button", { name: "跳过教程" })).toHaveCount(0);
  await sam.getByTestId("tour-exit").click();
  await expect(sam.getByTestId("dialog")).toContainText("还剩 6 步");
  await sam.getByTestId("dialog").getByRole("button", { name: "继续教程" }).click();
  await expect(bubble).toContainText("保留，还是恢复？");
  await sam.getByTestId("tour-exit").click();
  await sam.getByTestId("dialog").getByRole("button", { name: "先离开，下次接着走" }).click();
  await expect(sam.getByTestId("tour")).toHaveCount(0);
  await expect.poll(async () => (await (await again.request.get("/api/onboarding")).json()).tour).toBe("~rdecide");
  await sam.getByTestId("tour-resume").click();
  await expect(bubble).toContainText("保留，还是恢复？");
  // after the tour (finished or left at the end): 重新开始示例教程, the first cut as it was, the tour from the start
  await sam.request.put("/api/onboarding", { data: { tour: "" } });
  await sam.reload();
  await sam.getByTestId("tour-again").click();
  await sam.getByTestId("dialog").getByRole("button", { name: "重新开始" }).click();
  await expect(sam.getByTestId("tour-raw")).toBeVisible();

  // the end of the tour: before / after, and the way to their own first episode
  // 重新开始 reloads the page itself: jump to the end only once that reload has settled (Windows CI raced it)
  await sam.waitForLoadState("load");
  const done = sam.getByTestId("tour-done");
  await expect(async () => {
    await sam.request.put("/api/onboarding", { data: { tour: "done" } });
    await sam.reload();
    await expect(done).toContainText("同一段 30 秒，剪之前和剪之后", { timeout: 3000 });
  }).toPass({ timeout: 20000 });
  await done.getByTestId("tour-own").click();
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
  await sam.getByTestId("dialog").getByRole("button", { name: "删除" }).click();
  await expect(st.getByTestId("sample-open")).toHaveText("添加示例节目");
  await sam.goto("/#/");
  await expect(sam.getByTestId("onboard-card")).toBeVisible();
  // added again (Sam had finished the tour): a new sample, the tour from step 1 (Leon 2026-10-23)
  await sam.goto("/#/settings/general");
  await sam.getByTestId("onboard-settings").getByTestId("sample-open").click();
  await expect(sam).toHaveURL(/#\/ep\/SAMPLE_01\/review/);
  await expect(sam.getByTestId("tour-raw")).toContainText("先听听没剪过的样子");
});
