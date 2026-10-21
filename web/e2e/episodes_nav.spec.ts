import { expect, test } from "@playwright/test";

test.use({ baseURL: "http://127.0.0.1:8798" }); // the AI workspace holds one episode

// 「首页」 in the top bar goes back to the episode overview from any screen
test("episodes nav: link on every screen, selected on the overview", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/#\/ep\/.+\/listen/, { timeout: 20_000 }); // a single episode opens directly
  const link = page.locator(".topbar").getByRole("link", { name: "首页", exact: true });
  await expect(link).not.toHaveAttribute("aria-current", "page");
  await link.click();
  await expect(page).toHaveURL(/#\/$/);
  await expect(page.locator("h1.home-title")).toBeVisible();
  await expect(page.getByRole("heading", { name: "剧集", level: 2 })).toBeVisible();
  await expect(link).toHaveAttribute("aria-current", "page");

  // every top-bar page keeps its own link, selected, like 首页 (验收 V1)
  for (const [name, url] of [["素材库", /#\/library/], ["学到的规则", /#\/learning/], ["设置", /#\/settings/]] as const) {
    await page.locator(".topbar").getByRole("link", { name }).click();
    await expect(page).toHaveURL(url);
    const own = page.locator(".topbar").getByRole("link", { name });
    await expect(own).toBeVisible();
    await expect(own).toHaveAttribute("aria-current", "page");
    await expect(link).not.toHaveAttribute("aria-current", "page");
  }
  await link.click();
  await expect(page.locator("h1.home-title")).toBeVisible();
  await expect(page.getByRole("heading", { name: "剧集", level: 2 })).toBeVisible();
});
