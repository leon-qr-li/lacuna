import { expect, test } from "@playwright/test";
import { SCOPES_PORT } from "../playwright.config";

// 专有名词自动校对 (decision transcript-terms): an episode imported before is proofread by itself when it opens
// (nobody clicks); the corrected word shows right away, the audio version and the edits stay; the next opening
// asks nothing more. 系统专有名词 on 设置: one list for every project. Runs on the scopes server (fake proofreader:
// 今天 → Pei in its own episode only, tests/app/e2e/transcript_fix.py).
test.use({ baseURL: `http://127.0.0.1:${SCOPES_PORT}` });
const EP = "EP_TEST_校对";

test.describe.serial("transcript terms", () => {
  test("opening an old episode fixes a mis-heard name by itself, audio untouched", async ({ page }) => {
    const before = await (await page.request.get(`/api/episodes/${encodeURIComponent(EP)}`)).json();
    expect((await (await page.request.get(`/api/episodes/${encodeURIComponent(EP)}/transcript/fix`)).json()).due).toBe(true);
    await page.goto(`/#/ep/${encodeURIComponent(EP)}/listen`);
    const tx = page.getByTestId("ml-tx");
    await expect(page.getByText(/已按专有名词自动校对 \d+ 处：今天 → Pei/)).toBeVisible();
    await expect(tx.locator(".ml-w", { hasText: /^Pei$/ }).first()).toBeVisible();
    await expect(tx.locator(".ml-w", { hasText: /^今$/ })).toHaveCount(0);
    const after = await (await page.request.get(`/api/episodes/${encodeURIComponent(EP)}`)).json();
    expect(after.version).toBe(before.version);
    expect(after.edits.length).toBe(before.edits.length);
    expect((await (await page.request.get(`/api/episodes/${encodeURIComponent(EP)}/transcript/fix`)).json()).due).toBe(false);
    await expect(page.getByTestId("term-fix-busy")).toHaveCount(0);
  });

  test("系统专有名词 on 设置: starts with ChatGPT, saved for every project", async ({ page }) => {
    await page.goto("/#/settings");
    const box = page.getByTestId("system-terms-text");
    await expect(box).toHaveValue(/ChatGPT/);
    const was = await box.inputValue();
    await expect(page.getByTestId("system-terms-save")).toBeDisabled();
    await box.fill(`${was}\nSora`);
    await page.getByTestId("system-terms-save").click();
    await expect(page.getByText("已保存，之后打开的剧集会按新词表自动校对。")).toBeVisible();
    expect((await (await page.request.get("/api/app/terms")).json()).terms).toContain("Sora");
    await box.fill(was); // leave the server as it was
    await page.getByTestId("system-terms-save").click();
    await expect(page.getByTestId("system-terms-save")).toBeDisabled();
  });
});
