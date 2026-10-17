import { expect, test } from "@playwright/test";

// phase 8: bundled fonts (nothing fetched from the web) and the light / dark theme toggle
test("theme: follows the system, toggle switches and is remembered; fonts are bundled", async ({ page }) => {
  const external: string[] = [];
  page.on("request", (r) => {
    const u = new URL(r.url());
    if (u.hostname !== "127.0.0.1") external.push(r.url());
  });
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("/#/");
  await page.evaluate(() => localStorage.removeItem("lacuna.theme"));
  await page.reload();
  const html = page.locator("html");
  await expect(html).toHaveAttribute("data-theme", "dark");

  const toggle = page.getByTestId("theme-toggle");
  await toggle.click();
  await expect(html).toHaveAttribute("data-theme", "light");
  const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  expect(bg).toBe("rgb(244, 244, 248)");

  // remembered over the system preference, and on other screens
  await page.reload();
  await expect(html).toHaveAttribute("data-theme", "light");
  await page.goto("/#/settings");
  await expect(html).toHaveAttribute("data-theme", "light");
  await page.getByTestId("theme-toggle").click();
  await expect(html).toHaveAttribute("data-theme", "dark");

  // the Chinese and Latin faces load from the app itself
  await page.goto("/#/");
  await page.getByRole("heading", { name: "剧集" }).waitFor();
  const faces = await page.evaluate(async () => {
    await document.fonts.ready;
    return {
      cjk: document.fonts.check('16px "MiSans VF"', "剧集"),
      latin: document.fonts.check('16px "Inter Variable"', "LACUNA"),
    };
  });
  expect(faces).toEqual({ cjk: true, latin: true });
  expect(external).toEqual([]);
});
