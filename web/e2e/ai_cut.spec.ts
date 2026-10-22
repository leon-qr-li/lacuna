import { expect, test } from "@playwright/test";
import { undoKey } from "./undo";

// served by the second webServer in playwright.config.ts (an AI first-cut episode, short window)
test.use({ baseURL: "http://127.0.0.1:8798" });

test("AI first cut: no demo marks, review list in timeline order", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/#\/ep\/.+\/listen/, { timeout: 20_000 });
  await expect(page.locator(".ep-title")).toHaveText("合成 · AI 第一刀");
  await expect(page.locator(".banner")).toHaveCount(0);
  await expect(page.getByText("演示")).toHaveCount(0);

  await page.getByRole("link", { name: /审阅改动/ }).click();
  await expect(page).toHaveURL(/\/review$/);
  const items = page.getByTestId("review-list").locator(".ritem");
  await expect(items).toHaveCount(4);
  // timeline order, from the first second (not content-first / longest-first)
  const cats = ["filler", "interjection", "content", "content"];
  for (const [i, c] of cats.entries()) await expect(items.nth(i)).toHaveAttribute("data-category", c);
  await expect(items.first()).toHaveAttribute("aria-current", "true");
  // a content trim shows the AI's own reason and the struck words
  await items.nth(2).click();
  await expect(page.getByTestId("review-title")).toContainText("内容删减");
  await expect(page.getByText("这段题外话和主线无关，后面没有再提")).toBeVisible();
  await expect(page.locator(".struck").first()).toBeVisible();
  // the AI's unapplied suggestion (keep_flag) comes last here and can be applied
  await items.nth(3).click();
  await expect(page.getByTestId("review-title")).toContainText("AI 建议（未删）");
  await expect(page.getByRole("button", { name: "重新应用这个删除" })).toBeVisible();
  // routine cleanups are one line under the list, not listed one by one
  await expect(page.getByTestId("review-routine")).toContainText("另外收紧了");
});

test("review: decide → jump to next pending; Y shortcut; 全部通过 in one step, one undo", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: /审阅改动/ }).click();
  const items = page.getByTestId("review-list").locator(".ritem");
  await expect(items).toHaveCount(4);
  await expect(page.getByTestId("review-progress")).toContainText("已看 0 / 4");

  // keep the first: it is ticked and the second becomes current
  await expect(items.first()).toHaveAttribute("aria-current", "true");
  await page.getByRole("button", { name: /^保留/ }).click();
  await expect(page.locator(".toast")).toHaveText("已保留");
  await expect(items.nth(1)).toHaveAttribute("aria-current", "true");
  await expect(items.first().locator(".rstate")).toHaveText("✓");
  await expect(page.getByTestId("review-progress")).toContainText("已看 1 / 4");

  // the last is the AI's unapplied suggestion: Y confirms "don't cut" and wraps round to the skipped second
  await items.nth(3).click();
  await expect(page.getByRole("button", { name: "不删，保持原话" })).toBeVisible();
  await page.keyboard.press("y");
  await expect(page.locator(".toast")).toHaveText("已确认不删");
  await expect(items.nth(3).locator(".rstate")).toHaveText("不删 ✓");
  await expect(items.nth(1)).toHaveAttribute("aria-current", "true");

  // approve the remaining two in one go
  await page.getByTestId("review-keep-rest").click();
  await expect(page.locator(".toast")).toContainText("已全部通过 2 处，Ctrl+Z 可撤销");
  await expect(page.getByTestId("review-progress")).toContainText("已看 4 / 4");
  await expect(page.getByTestId("review-keep-rest")).toHaveCount(0);
  await expect(page.getByRole("link", { name: /审阅改动/ })).toHaveText("审阅改动 · 0");

  // one undo (the toast's 撤销) takes back exactly the batch, then the two single decisions
  await page.getByTestId("toast-undo").click();
  await expect(page.getByTestId("review-progress")).toContainText("已看 2 / 4");
  await undoKey(page);
  await expect(page.getByTestId("review-progress")).toContainText("已看 1 / 4");
  await undoKey(page);
  await expect(page.getByTestId("review-progress")).toContainText("已看 0 / 4");
});
