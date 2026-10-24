import { expect, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";

// 用户反馈 (decision 2026-10-24-user-feedback) on the default server with accounts: the top-bar 反馈 panel with
// its screenshot and page details, 我的反馈 with the owner's reply and the red dot (and the reply mail), 「告诉我们」
// on an export error, the 自动发布 card's link, the one question after an export, a new show's two questions.
const PW = "correct horse battery";
const SHOTS = process.env.FEEDBACK_SHOTS; // folder for review screenshots (optional)

test.describe.configure({ mode: "serial" });
test.beforeAll(async ({ request }) => {
  await request.post("/api/auth/_test/reset?skip_setup=false");
});
test.afterAll(async ({ request }) => {
  await request.post("/api/auth/_test/reset?skip_setup=true");
});

async function signIn(browser: Browser, email: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await page.goto("/");
  await page.getByTestId("auth-email").fill(email);
  await page.getByTestId("auth-password").fill(PW);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.locator(".topbar")).toBeVisible();
  return page;
}

async function mails(request: APIRequestContext, to: string) {
  const all = (await (await request.get("/api/auth/_test/outbox")).json()).mails as { to: string; subject: string; text: string }[];
  return all.filter((m) => m.to === to);
}

let leon: Page;

test("反馈: a problem with its screenshot and page; the owner's reply comes back with a red dot and a mail", async ({ browser, request }) => {
  const lc = await browser.newContext();
  leon = await lc.newPage();
  expect((await leon.request.post("/api/auth/register", { data: { email: "leon@example.com", password: PW, name: "Leon" } })).ok()).toBeTruthy();
  const inv = await (await leon.request.post("/api/auth/invites", { data: { email: "mia@example.com", plan: "basic" } })).json();
  const reg = await (await browser.newContext()).newPage();
  expect((await reg.request.post("/api/auth/register", { data: { invite: inv.link.split("/").at(-1), password: PW, name: "Mia" } })).ok()).toBeTruthy();

  const mia = await signIn(browser, "mia@example.com");
  await mia.getByTestId("feedback-open").click();
  const panel = mia.getByTestId("feedback-panel");
  await expect(panel).toBeVisible();
  // 遇到问题 is first: a picture of the page as it was, the page and the last steps attached
  await expect(panel.getByTestId("feedback-kind-bug")).toHaveAttribute("aria-checked", "true");
  await expect(panel.getByTestId("feedback-shot").locator("img")).toBeVisible({ timeout: 15000 });
  await expect(panel.getByTestId("feedback-shot-use")).toBeChecked();
  await expect(panel.getByTestId("feedback-context")).toContainText("最近");
  await expect(panel.getByTestId("feedback-send")).toBeDisabled();
  await panel.getByTestId("feedback-text").fill("导出到一半卡住了，进度条一直停在 80%。");
  // 在图上圈出来
  await panel.getByTestId("feedback-annotate-open").click();
  const canvas = mia.getByTestId("feedback-annotate-canvas");
  const box = (await canvas.boundingBox())!;
  await mia.mouse.move(box.x + 40, box.y + 40);
  await mia.mouse.down();
  await mia.mouse.move(box.x + 160, box.y + 90, { steps: 8 });
  await mia.mouse.up();
  await mia.getByTestId("feedback-annotate-done").click();
  await expect(mia.getByTestId("feedback-annotate")).toHaveCount(0);
  if (SHOTS) await mia.screenshot({ path: `${SHOTS}/panel-bug.png` });
  await panel.getByTestId("feedback-send").click();
  await expect(panel.getByTestId("feedback-sent")).toContainText("收到了，谢谢你");
  await expect(panel.getByTestId("feedback-sent")).toContainText("1 小时");
  await panel.getByRole("button", { name: "看我的反馈" }).click();
  const item = panel.getByTestId("feedback-item");
  await expect(item).toHaveCount(1);
  await expect(item).toContainText("导出到一半卡住了");
  await expect(item.getByTestId("feedback-status")).toHaveText("已收到");
  await expect(item).toContainText("有截图");

  // the owner sees it with the page, the steps and the picture (the admin's list, owner only)
  const all = (await (await leon.request.get("/api/feedback/all")).json()).items as { id: string; shot: boolean; context: { page: string; actions: string[] }; email: string }[];
  expect(all).toHaveLength(1);
  expect(all[0].email).toBe("mia@example.com");
  expect(all[0].shot).toBe(true);
  expect(all[0].context.page).toBe("#/");
  expect(all[0].context.actions.length).toBeGreaterThan(0);
  expect((await leon.request.get(`/api/feedback/${all[0].id}/shot`)).headers()["content-type"]).toContain("image/jpeg");
  expect((await mia.request.get("/api/feedback/all")).status()).toBe(403);

  // the owner answers: Mia gets a mail, a red dot on 反馈, the reply in 我的反馈; looking clears the dot
  const r = await leon.request.post(`/api/feedback/${all[0].id}/reply`, { data: { text: "已经修好了，谢谢你截的图。", status: "fixed", adopted: true } });
  expect((await r.json()).mailed).toBe(true);
  const mail = (await mails(request, "mia@example.com")).at(-1)!;
  expect(mail.subject).toBe("你的 LACUNA 反馈有回复了");
  expect(mail.text).toContain("已经修好了");
  expect(mail.text).toContain("#/feedback");
  await mia.keyboard.press("Escape");
  await mia.reload();
  await expect(mia.getByTestId("feedback-dot")).toBeVisible();
  await mia.getByTestId("feedback-open").click();             // with an answer waiting it opens on 我的反馈
  const mine = mia.getByTestId("feedback-mine");
  await expect(mine.getByTestId("feedback-reply")).toContainText("已经修好了，谢谢你截的图。");
  await expect(mine.getByTestId("feedback-status")).toHaveText("已修好");
  await expect(mine.getByTestId("feedback-adopted")).toContainText("1 小时");
  if (SHOTS) await mia.screenshot({ path: `${SHOTS}/mine.png` });
  await expect(mia.getByTestId("feedback-dot")).toHaveCount(0);
  // the mail's link: 我的反馈 as a page
  await mia.goto("/#/feedback");
  await expect(mia.locator(".fb-page").getByTestId("feedback-item")).toContainText("导出到一半卡住了");
});

test("反馈: an idea and a compliment, with how much it matters and leave to quote it", async ({ browser }) => {
  const mia = await signIn(browser, "mia@example.com");
  await mia.getByTestId("feedback-open").click();
  const panel = mia.getByTestId("feedback-panel");
  await panel.getByTestId("feedback-kind-idea").click();
  await expect(panel).toContainText("你希望 LACUNA 能做什么？");
  await expect(panel.getByTestId("feedback-shot")).toHaveCount(0);
  await panel.getByTestId("feedback-text").fill("希望能直接发到 Buzzsprout");
  await panel.getByRole("button", { name: "很需要" }).click();
  await panel.getByTestId("feedback-send").click();
  await expect(panel.getByTestId("feedback-sent")).toBeVisible();
  await panel.getByRole("tab", { name: "写反馈" }).click();
  await panel.getByTestId("feedback-kind-praise").click();
  await expect(panel.getByTestId("feedback-quote")).toContainText("同意我们公开引用这段话");
  await panel.getByTestId("feedback-text").fill("口癖去得很干净");
  await panel.getByTestId("feedback-quote").getByRole("checkbox").check();
  await panel.getByTestId("feedback-send").click();
  await expect(panel.getByTestId("feedback-sent")).toBeVisible();
  const all = (await (await leon.request.get("/api/feedback/all")).json()).items as { kind: string; importance?: string; quote_ok?: boolean }[];
  expect(all.find((i) => i.kind === "idea")!.importance).toBe("need");
  expect(all.find((i) => i.kind === "praise")!.quote_ok).toBe(true);
});

test("「告诉我们」 on an export error opens the panel filled in", async () => {
  await leon.route("**/api/episodes/*/export", (route) =>
    route.request().method() === "POST" ? route.fulfill({ status: 500, json: { detail: "混音这一步出错了" } }) : route.continue(),
  );
  await leon.goto("/#/ep/EP_TEST_合成/export");
  await leon.getByTestId("export-start").click();
  const tell = leon.getByTestId("feedback-tellus");
  await expect(tell).toBeVisible();
  await tell.click();
  const panel = leon.getByTestId("feedback-panel");
  await expect(panel.getByTestId("feedback-prefill")).toContainText("导出没有完成");
  await expect(panel.getByTestId("feedback-prefill")).toContainText("混音这一步出错了");
  await expect(panel.getByTestId("feedback-send")).toBeEnabled();     // nothing more to write
  await panel.getByTestId("feedback-send").click();
  await expect(panel.getByTestId("feedback-sent")).toBeVisible();
  await panel.getByTestId("feedback-done").click();
  await expect(panel).toHaveCount(0);
  await leon.unroute("**/api/episodes/*/export");
  const all = (await (await leon.request.get("/api/feedback/all")).json()).items as { source: string; text: string; context: { episode?: string; actions: string[] } }[];
  const it = all.find((i) => i.source === "error")!;
  expect(it.text).toContain("混音这一步出错了");
  expect(it.context.episode).toBe("EP_TEST_合成");
  expect(it.context.actions.some((a) => a.includes("/export → 500"))).toBe(true);
});

test("自动发布's 告诉我们 opens the panel as an idea with the platforms picked", async () => {
  await leon.goto("/#/project/publish");
  const box = leon.getByTestId("show-auto-publish");
  await box.getByTestId("auto-publish-spotify").check();
  await box.getByTestId("auto-publish-feedback").click();
  const panel = leon.getByTestId("feedback-panel");
  await expect(panel.getByTestId("feedback-kind-idea")).toHaveAttribute("aria-checked", "true");
  await expect(panel.getByTestId("feedback-prefill")).toContainText("Spotify");
  await expect(panel).toContainText("你希望发布这一步怎么做？");
  await panel.getByTestId("feedback-text").fill("我用 Buzzsprout");
  await panel.getByTestId("feedback-send").click();
  await expect(panel.getByTestId("feedback-sent")).toBeVisible();
  const all = (await (await leon.request.get("/api/feedback/all")).json()).items as { source: string; platforms: string[] }[];
  expect(all.find((i) => i.source === "publish")!.platforms).toEqual(["Spotify"]);
  await panel.getByTestId("feedback-done").click();
  await box.getByTestId("auto-publish-spotify").uncheck();
});

test("one question after an export finishes: 评分, and 以后再说 / 不再问我 are kept", async () => {
  // which question is the server's call (tests/app/test_feedback.py); here: the card and its answer
  await leon.route("**/api/feedback/prompt", (route) =>
    route.request().method() === "GET" ? route.fulfill({ json: { ask: "rate" } }) : route.continue(),
  );
  await leon.goto("/#/ep/EP_TEST_合成/export");
  await leon.getByTestId("export-start").click();
  const card = leon.getByTestId("feedback-prompt-rate");
  await expect(card).toBeVisible({ timeout: 30000 });
  await expect(card).toContainText("这集剪得怎么样？");
  await expect(card.getByTestId("feedback-prompt-send")).toBeDisabled();
  await card.getByTestId("feedback-star-4").click();
  await card.getByRole("button", { name: "1–2 小时" }).click();
  await card.locator("textarea").fill("有两处笑声被剪短了。");
  if (SHOTS) await leon.screenshot({ path: `${SHOTS}/rate.png` });
  await card.getByTestId("feedback-prompt-send").click();
  await expect(card).toContainText("谢谢你");
  await expect(card).toHaveCount(0, { timeout: 5000 });
  await leon.unroute("**/api/feedback/prompt");
  const all = (await (await leon.request.get("/api/feedback/all")).json()).items as { kind: string; stars?: number; saved?: string; text: string }[];
  const rate = all.find((i) => i.kind === "rate")!;
  expect(rate.stars).toBe(4);
  expect(rate.saved).toBe("1-2h");
  // answered: the real server doesn't ask it again
  expect((await (await leon.request.get("/api/feedback/prompt")).json()).ask).toBeNull();
});

test("a new show's setup asks two optional questions, kept for the owner", async ({ browser }) => {
  const mia = await signIn(browser, "mia@example.com");
  await mia.goto("/#/");
  const welcome = mia.getByTestId("welcome-own");
  if (await welcome.isVisible().catch(() => false)) await welcome.click();
  const setup = mia.getByTestId("show-setup");
  await expect(setup.getByTestId("show-questions")).toContainText("让我们更了解你的节目");
  await setup.getByTestId("show-name").fill("夜航电台");
  await setup.getByLabel("第 1 位主持人的名字").fill("Mia");
  await setup.getByTestId("show-q-region-na").click();
  await setup.getByTestId("show-q-editing-self").click();
  await setup.getByTestId("show-save").click();
  await expect(mia.getByTestId("show-setup")).toHaveCount(0);
  await mia.getByTestId("feedback-open").click();
  await mia.getByTestId("feedback-text").fill("新节目建好了");
  await mia.getByTestId("feedback-send").click();
  await expect(mia.getByTestId("feedback-sent")).toBeVisible();
  const all = (await (await leon.request.get("/api/feedback/all")).json()).items as { text: string; profile: { region?: string; editing?: string; lang?: string } | null }[];
  const it = all.find((i) => i.text === "新节目建好了")!;
  expect(it.profile).toMatchObject({ region: "na", editing: "self", lang: "zh" });
});

test("全部反馈（临时）: the owner answers from the list; the person sees it", async ({ browser }) => {
  await leon.goto("/#/feedback");
  await leon.getByTestId("feedback-all-link").first().click();
  const row = leon.getByTestId("feedback-all-item").filter({ hasText: "希望能直接发到 Buzzsprout" });
  await expect(row).toContainText("mia@example.com");
  await row.getByTestId("feedback-all-text").fill("在计划里了，beta 之后做。");
  await row.getByTestId("feedback-all-status").selectOption("planned");
  await row.getByTestId("feedback-all-send").click();
  await expect(row).toContainText("已保存，已发邮件给对方");
  await expect(row).toContainText("在计划里了，beta 之后做。");
  if (SHOTS) await leon.screenshot({ path: `${SHOTS}/all.png`, fullPage: true });
  // 验收 helper: ask an account the prompts again
  await leon.getByTestId("feedback-reset-email").fill("leon@example.com");
  await leon.getByTestId("feedback-reset").click();
  await expect(leon.getByTestId("feedback-all")).toContainText("已重置");
  const mia = await signIn(browser, "mia@example.com");
  await mia.goto("/#/feedback");
  const item = mia.getByTestId("feedback-item").filter({ hasText: "希望能直接发到 Buzzsprout" });
  await expect(item.getByTestId("feedback-status")).toHaveText("在计划中");
  await expect(item.getByTestId("feedback-reply")).toContainText("在计划里了");
  // not for anyone else
  await expect(mia.getByTestId("feedback-all-link")).toHaveCount(0);
  expect((await mia.request.get("/api/feedback/all")).status()).toBe(403);
});
