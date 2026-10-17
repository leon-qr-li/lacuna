import { expect, test } from "@playwright/test";

// served by the second webServer in playwright.config.ts (an AI first-cut episode, short window)
test.use({ baseURL: "http://127.0.0.1:8798" });

test("AI first cut: no demo marks, content trims lead the review list", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/#\/ep\/.+\/listen/);
  await expect(page.locator(".ep-title")).toHaveText("合成 · AI 第一刀");
  await expect(page.getByText(/^第一刀已完成 · \d+ 处待你过目$/)).toBeVisible();
  await expect(page.locator(".banner")).toHaveCount(0);
  await expect(page.getByText("演示")).toHaveCount(0);

  await page.getByRole("link", { name: /改动审阅/ }).click();
  await expect(page).toHaveURL(/\/review$/);
  const items = page.getByTestId("review-list").locator(".ritem");
  await expect(items).toHaveCount(4);
  await expect(items.first()).toHaveAttribute("data-category", "content");
  await expect(items.nth(1)).toHaveAttribute("data-category", "content");
  await expect(items.nth(2)).not.toHaveAttribute("data-category", "content");
  // the first (longest) content trim is selected, with the AI's own reason and the struck words
  await expect(page.getByTestId("review-title")).toContainText("内容删减");
  await expect(page.getByText("这段题外话和主线无关，后面没有再提")).toBeVisible();
  await expect(page.locator(".struck").first()).toBeVisible();
  // the AI's unapplied suggestion (keep_flag) is second and can be applied
  await items.nth(1).click();
  await expect(page.getByTestId("review-title")).toContainText("AI 建议（未删）");
  await expect(page.getByRole("button", { name: "重新应用这个删除" })).toBeVisible();
  // routine cleanups are grouped by category, not listed one by one
  await expect(page.locator(".routine")).toContainText("停顿收紧");
  await expect(page.locator(".routine")).toContainText("口误与无意识重复");
});
