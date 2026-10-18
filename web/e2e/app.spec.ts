import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";

const audioTime = (page: Page) =>
  page.getByTestId("main-audio").evaluate((a: HTMLAudioElement) => a.currentTime);

async function openEpisode(page: Page) {
  await page.goto("/");
  // a single episode in the workspace opens straight into Full Listen
  await expect(page).toHaveURL(/#\/ep\/.+\/listen/, { timeout: 20_000 });
  await expect(page.locator(".ep-title")).toHaveText("合成测试集");
  await expect(page.getByTestId("main-audio")).toHaveAttribute("src", /\/audio\/.+\.wav$/);
}

test.describe.serial("LACUNA Studio", () => {
  test("open episode shows workspace, lanes and demo banner", async ({ page }) => {
    await openEpisode(page);
    await expect(page.getByText("第一刀（演示）已完成 · 1 处待你过目")).toBeVisible();
    await expect(page.locator(".banner")).toContainText("合成测试数据");
    await expect(page.getByTestId("lane-Leon")).toBeVisible();
    await expect(page.getByTestId("lane-Pei")).toBeVisible();
    await expect(page.getByTestId("clock")).toContainText("/ 0:52");
    await expect(page.getByRole("heading", { name: "这附近改了什么" })).toBeVisible();
  });

  test("play / pause", async ({ page }) => {
    await openEpisode(page);
    await page.getByLabel("暂停时回退 5 秒").uncheck();
    await page.getByTestId("play").click();
    await expect.poll(() => audioTime(page), { timeout: 10_000 }).toBeGreaterThan(0.6);
    await expect(page.getByTestId("play")).toHaveAttribute("aria-label", "暂停");
    await page.getByTestId("play").click();
    await expect(page.getByTestId("play")).toHaveAttribute("aria-label", "播放");
    const t = await audioTime(page);
    await page.waitForTimeout(400);
    expect(await audioTime(page)).toBeCloseTo(t, 2);
    expect(await page.getByTestId("main-audio").evaluate((a: HTMLAudioElement) => a.paused)).toBe(true);
  });

  test("1.5x keeps position and pitch preservation", async ({ page }) => {
    await openEpisode(page);
    await page.getByLabel("暂停时回退 5 秒").uncheck();
    await page.getByTestId("play").click();
    await expect.poll(() => audioTime(page), { timeout: 10_000 }).toBeGreaterThan(1.0);
    const before = await audioTime(page);
    await page.getByRole("button", { name: "1.5×" }).click();
    await expect(page.getByRole("button", { name: "1.5×" })).toHaveAttribute("aria-pressed", "true");
    const state = await page
      .getByTestId("main-audio")
      .evaluate((a: HTMLAudioElement) => ({ rate: a.playbackRate, pitch: a.preservesPitch, t: a.currentTime }));
    expect(state.rate).toBe(1.5);
    expect(state.pitch).toBe(true);
    expect(state.t).toBeGreaterThanOrEqual(before);
    await page.getByTestId("play").click();
  });

  test("switch modes shares the playhead; review keyboard works", async ({ page }) => {
    await openEpisode(page);
    await page.getByRole("link", { name: /审阅改动/ }).click();
    await expect(page).toHaveURL(/\/review$/);
    await expect(page.getByTestId("review-title")).toHaveText("删除 4.4 秒 · 题外话");
    await expect(page.getByRole("region", { name: "原文对照" })).toBeVisible();
    await expect(page.locator(".struck").first()).toBeVisible();
    await expect(page.getByRole("button", { name: /A · 原始/ })).toBeEnabled();
    // shared playhead: selecting an edit moves the main player there
    await expect.poll(() => audioTime(page)).toBeCloseTo(25.2, 0);
    // R restores, undo brings the cut back
    await page.keyboard.press("r");
    await expect(page.locator(".toast")).toHaveText("已恢复原话");
    await expect(page.getByRole("button", { name: "重新应用这个删除" })).toBeVisible();
    await page.getByRole("button", { name: "撤销" }).click();
    await expect(page.getByRole("button", { name: "保留这个删除" })).toBeVisible();
    await page.getByRole("link", { name: "整集试听", exact: true }).click();
    await expect(page.getByTestId("play")).toBeVisible();
    await expect.poll(() => audioTime(page)).toBeCloseTo(25.2, 0);
  });

  test("slow audio stream: the playhead survives restore → undo → back to Full Listen", async ({ page }) => {
    // regression (macOS CI): a seek set while the new version's stream is not yet seekable was dropped to 0.
    // Delaying the audio responses reproduces that race on any OS.
    let n = 0;
    await page.route("**/audio/**", async (route) => {
      await new Promise((r) => setTimeout(r, [300, 1200, 700][n++ % 3]));
      await route.continue();
    });
    await openEpisode(page);
    await page.getByRole("link", { name: /审阅改动/ }).click();
    await expect(page.getByTestId("review-title")).toHaveText("删除 4.4 秒 · 题外话");
    await expect.poll(() => audioTime(page), { timeout: 10_000 }).toBeCloseTo(25.2, 0);
    await page.keyboard.press("r");
    await expect(page.locator(".toast")).toHaveText("已恢复原话");
    await page.getByRole("button", { name: "撤销" }).click();
    await expect(page.getByRole("button", { name: "保留这个删除" })).toBeVisible();
    await page.getByRole("link", { name: "整集试听", exact: true }).click();
    await expect.poll(() => audioTime(page), { timeout: 10_000 }).toBeCloseTo(25.2, 0);
    await expect(page.getByTestId("clock")).toContainText("0:25");
  });

  test("chat command → preview → approve → edit appears; undo removes it", async ({ page }) => {
    await openEpisode(page);
    await page.getByRole("slider", { name: "播放位置" }).fill("15.5");
    await expect(page.locator(".at-chip")).toHaveText("@ 0:15");
    await page.getByLabel(/对 AI 制作人说/).fill("这里停顿短一点");
    await page.keyboard.press("Enter");
    const proposal = page.getByTestId("proposal");
    await expect(proposal).toBeVisible();
    await expect(page.getByTestId("chat-log")).toContainText("停顿从 2.0 秒收到 0.4 秒");
    await expect(page.locator(".mark-pending").first()).toBeVisible();

    await proposal.getByRole("button", { name: "试听前后对比" }).click();
    const after = proposal.getByRole("button", { name: /改后/ });
    await expect(after).toBeEnabled();
    await after.click();
    await expect
      .poll(() => proposal.getByTestId("ab-audio").evaluate((a: HTMLAudioElement) => !a.paused && a.currentTime > 0))
      .toBe(true);

    await proposal.getByRole("button", { name: "批准" }).click();
    await expect(page.getByText("✓ 已批准并应用")).toBeVisible();
    const chatEdit = page.locator('[data-testid=nearby] li[data-source="chat"]');
    await expect(chatEdit).toContainText("停顿 2.0s → 0.4s");
    await expect(page.getByTestId("clock")).toContainText("/ 0:50");

    await page.getByRole("button", { name: "撤销" }).click();
    await expect(page.locator(".toast")).toContainText("已撤销");
    await expect(chatEdit).toHaveCount(0);
    await expect(page.getByTestId("clock")).toContainText("/ 0:52");

    // the conversation survives a round trip through Edit Review
    await page.getByRole("link", { name: /审阅改动/ }).click();
    await page.getByRole("link", { name: "整集试听", exact: true }).click();
    await expect(page.getByTestId("chat-log")).toContainText("✓ 已批准并应用");
  });

  test("export the current version as MP3 + WAV", async ({ page }) => {
    await openEpisode(page);
    await page.getByTestId("export-toggle").click(); // 导出 is a step of the flow (phase 8)
    await expect(page.getByRole("navigation", { name: "制作流程" }).locator('[aria-current="page"]')).toHaveText("导出");
    const pop = page.locator('[aria-label="导出成品"]');
    await expect(pop).toContainText("−16 LUFS");
    await pop.getByTestId("export-start").click();
    const result = pop.getByTestId("export-result");
    await expect(result).toBeVisible({ timeout: 30_000 });
    await expect(result).toContainText(/响度\s*-1[56]\.\d LUFS/);
    const links = result.locator(".export-files a");
    await expect(links).toHaveCount(2);
    await expect(links.filter({ hasText: /\.mp3$/ })).toHaveCount(1);
    const download = page.waitForEvent("download");
    await links.filter({ hasText: /\.wav$/ }).click();
    const dl = await download;
    expect(await dl.failure()).toBeNull();
    // (the suggested name is locale-dependent in headless Chromium for Chinese ids; check bytes)
    const head = readFileSync((await dl.path())!).subarray(0, 4).toString("latin1");
    expect(head).toBe("RIFF");
    await page.screenshot({ path: "test-results/export.png" });
  });
});
