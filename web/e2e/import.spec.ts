import { expect, test } from "@playwright/test";

// served by the third webServer in playwright.config.ts: empty workspace, raw tracks in ./recordings,
// fake ASR + fake Claude first cut (the rest - decoding, features, op conversion, episode - is real)
test.use({ baseURL: "http://127.0.0.1:8797" });

test("import a new episode: pick two tracks → progress → straight into review", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("工作区里还没有剧集")).toBeVisible();
  await page.getByRole("button", { name: "导入新一集" }).click();
  await expect(page.getByTestId("import-id")).toHaveValue("EP001");
  await page.getByTestId("import-title").fill("EP001 · 导入测试");

  // pick Leon's track in the folder browser; Pei's is guessed from the same folder
  await page.getByRole("button", { name: "选择文件…" }).first().click();
  const browser = page.getByRole("dialog", { name: "选择分轨文件" });
  await browser.getByRole("button", { name: /recordings/ }).click();
  await browser.getByRole("button", { name: /Leon\.wav/ }).click();
  await expect(browser).toHaveCount(0);
  await expect(page.getByTestId("import-leon")).toHaveText("Leon.wav");
  await expect(page.getByTestId("import-pei")).toHaveText("Pei.wav");

  await page.getByRole("button", { name: "开始导入" }).click();
  const job = page.getByTestId("import-job");
  await expect(job).toHaveAttribute("data-state", /queued|running/);
  await expect(job.getByRole("progressbar")).toBeVisible();
  await expect(page.getByTestId("import-stage")).toContainText("AI 第一刀");
  await expect(page.getByRole("button", { name: "导入新一集" })).toBeDisabled(); // one import at a time

  // done → the app opens the review by itself
  await expect(page).toHaveURL(/#\/ep\/EP001\/review$/, { timeout: 30_000 });
  await expect(page.locator(".ep-title")).toHaveText("EP001 · 导入测试");
  const items = page.getByTestId("review-list").locator(".ritem");
  await expect(items).toHaveCount(2);
  // timeline order: the earlier filler comes first, the content trim after it
  await expect(items.nth(1)).toHaveAttribute("data-category", "content");
  await items.nth(1).click();
  await expect(page.getByText("这段题外话和主线无关，后面没有再提")).toBeVisible();

  // back home (no auto-redirect): the task shows as done with a link to the review
  await page.locator("a.brand").click();
  await expect(page.getByTestId("import-job")).toHaveAttribute("data-state", "done");
  await expect(page.getByTestId("import-job")).toContainText("2 处需要你过目");
  await expect(page.locator(".ep-list")).toContainText("EP001 · 导入测试");
  await page.getByRole("link", { name: "开始审阅" }).click();
  await expect(page).toHaveURL(/#\/ep\/EP001\/review$/);
});
