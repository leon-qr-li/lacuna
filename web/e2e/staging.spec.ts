import { expect, test } from "@playwright/test";

// the staging site (decision staging-site) marks itself; the real site and the desktop app don't
test("the staging site says so in the top bar and the tab title", async ({ page }) => {
  await page.route("**/api/app", async (route) => {
    const res = await route.fetch();
    await route.fulfill({ response: res, json: { ...(await res.json()), cloud: true, staging: true } });
  });
  await page.goto("/");
  await expect(page.getByTestId("staging-badge")).toHaveText("预览站");
  await expect(page).toHaveTitle(/^预览站 · /);
});

test("no staging mark elsewhere", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator(".topbar")).toBeVisible();
  await expect(page.getByTestId("staging-badge")).toHaveCount(0);
  await expect(page).not.toHaveTitle(/预览站/);
});
