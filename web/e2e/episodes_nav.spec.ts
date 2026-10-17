import { expect, test } from "@playwright/test";

test.use({ baseURL: "http://127.0.0.1:8798" }); // the AI workspace holds one episode

// 「剧集」 in the top bar goes back to the episode overview from any screen
test("episodes nav: link on every screen, selected on the overview", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/#\/ep\/.+\/listen/); // a single episode opens directly
  const link = page.locator(".topbar").getByRole("link", { name: "剧集", exact: true });
  await expect(link).not.toHaveAttribute("aria-current", "page");
  await link.click();
  await expect(page).toHaveURL(/#\/$/);
  await expect(page.getByRole("heading", { name: "剧集", level: 1 })).toBeVisible();
  await expect(link).toHaveAttribute("aria-current", "page");

  await page.locator(".topbar").getByRole("link", { name: "素材库" }).click();
  await expect(page).toHaveURL(/#\/library/);
  await expect(link).not.toHaveAttribute("aria-current", "page");
  await link.click();
  await expect(page.getByRole("heading", { name: "剧集", level: 1 })).toBeVisible();
});
