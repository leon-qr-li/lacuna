import { expect, test } from "@playwright/test";
import { SCOPES_PORT } from "../playwright.config";

// 校对专有名词 (decision transcript-terms): the chip on 文字稿剪辑 proofreads an episode imported before against the
// show's names; the corrected word shows right away, the audio version and the edits stay. Runs on the scopes server
// (fake proofreader: 今天 → Pei, tests/app/e2e/transcript_fix.py) on its second episode.
test.use({ baseURL: `http://127.0.0.1:${SCOPES_PORT}` });
const EP = "EP_TEST_另一集";

test("proofreading fixes a mis-heard name in the transcript, audio untouched", async ({ page }) => {
  const before = await (await page.request.get(`/api/episodes/${encodeURIComponent(EP)}`)).json();
  await page.goto(`/#/ep/${encodeURIComponent(EP)}/listen`);
  const tx = page.getByTestId("ml-tx");
  await expect(tx.locator(".ml-w", { hasText: /^今$/ }).first()).toBeVisible();
  await page.getByTestId("term-fix-btn").click();
  await expect(page.getByText(/已校对 \d+ 处：今天 → Pei/)).toBeVisible();
  await expect(tx.locator(".ml-w", { hasText: /^Pei$/ }).first()).toBeVisible();
  await expect(tx.locator(".ml-w", { hasText: /^今$/ })).toHaveCount(0);
  const after = await (await page.request.get(`/api/episodes/${encodeURIComponent(EP)}`)).json();
  expect(after.version).toBe(before.version);
  expect(after.edits.length).toBe(before.edits.length);
  // nothing left: a second pass says so
  await page.getByTestId("term-fix-btn").click();
  await expect(page.getByText("没有找到听错的专有名词")).toBeVisible();
});
