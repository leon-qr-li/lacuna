import { expect, test, type Page } from "@playwright/test";

// Batch 7 (visual walkthrough + copy sweep): the fixes Leon picked, as they look on screen.
const EP = encodeURIComponent("EP_TEST_合成");

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1);

test("B8: the music page has one player of our own, no browser controls", async ({ page }) => {
  await page.goto(`/#/ep/${EP}/music`);
  const audio = page.getByTestId("mix-audio");
  await expect(audio).toHaveCount(1);
  expect(await audio.evaluate((a: HTMLAudioElement) => a.controls)).toBe(false);
  const play = page.getByTestId("mix-play");
  await expect(play).toHaveAccessibleName("播放");
  await play.click();
  await expect.poll(() => audio.evaluate((a: HTMLAudioElement) => a.paused)).toBe(false);
  await expect(play).toHaveAccessibleName("暂停");
  await play.click();
  await expect.poll(() => audio.evaluate((a: HTMLAudioElement) => a.paused)).toBe(true);
  await expect(page.getByRole("button", { name: "后退 5 秒" }).first()).toHaveText("−5 秒");
});

test("B18: the theme hint follows the choice", async ({ page }) => {
  await page.goto("/#/settings/general");
  const hint = page.getByTestId("theme-hint");
  await page.getByRole("radio", { name: "深色" }).click();
  await expect(hint).toContainText("一直用深色");
  await page.getByRole("radio", { name: "浅色" }).click();
  await expect(hint).toContainText("一直用浅色");
  await page.getByRole("radio", { name: "跟随系统" }).click();
  await expect(hint).toContainText("跟随系统");
});

test("B13: before an export the standards card says it will be done, not that it was", async ({ page }) => {
  await page.goto(`/#/ep/${EP}/export`);
  const std = page.getByTestId("export-standard");
  await expect(std).toContainText("播客平台标准");
  await expect(page.getByTestId("export-standard-note")).toContainText("导出时会处理到播客平台标准");
});

test("B26: under 1280 wide the LACUNA panel starts closed and pushes the page when opened", async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 768 });
  await page.goto(`/#/ep/${EP}/listen`);
  const chat = page.getByRole("region", { name: "LACUNA 对话" });
  await expect(page.getByTestId("chat-open")).toBeVisible();
  await expect(chat).toBeHidden();
  const center = page.locator(".workspace > .center");
  const wide = (await center.boundingBox())!.width;
  await page.getByTestId("chat-open").click();
  await expect(chat).toBeVisible();
  const c = (await center.boundingBox())!;
  const p = (await chat.boundingBox())!;
  expect(c.width).toBeLessThan(wide - 200);           // pushed over, not covered
  expect(p.x).toBeGreaterThanOrEqual(c.x + c.width - 1);
  const bar = (await page.locator(".topbar").boundingBox())!;
  expect(p.y).toBeGreaterThanOrEqual(bar.y + bar.height); // never over the top bar
});

test("T9: on a phone the top bar folds into a menu and pages fit the width", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/#/settings");
  const toggle = page.getByTestId("menu-toggle");
  await expect(toggle).toBeVisible();
  await expect(page.locator(".topbar").getByRole("link", { name: "设置" })).toBeHidden();
  await toggle.click();
  await expect(page.locator(".topbar").getByRole("link", { name: "设置" })).toBeVisible();
  for (const path of ["/#/settings", `/#/ep/${EP}/export`, `/#/ep/${EP}/levels`, `/#/ep/${EP}/listen`, "/#/feedback"]) {
    await page.goto(path);
    await page.waitForTimeout(400);
    expect(await noSideScroll(page), path).toBe(true);
  }
});

test("B9: the feedback page has one 写新反馈", async ({ page }) => {
  await page.goto("/#/feedback");
  await expect(page.getByRole("heading", { name: "我的反馈" })).toBeVisible();
  await expect(page.getByRole("button", { name: "写新反馈" })).toHaveCount(1);
});

test("T3: episode tiles carry a status stripe", async ({ page }) => {
  await page.goto("/#/");
  const tile = page.getByTestId("episode").first();
  await expect(tile.getByTestId("episode-stripe")).toHaveAttribute("data-stage", /review|reviewed|exported/);
});
