import { expect, test } from "@playwright/test";

// the LACUNA Studio logo (features/brand/logo.svg): favicon + top-bar mark, served with the app
test("brand: favicon and top-bar logo come from the bundled logo.svg", async ({ page, request }) => {
  await page.goto("/#/");
  const href = await page.locator('link[rel="icon"]').getAttribute("href");
  expect(href).toMatch(/^\/assets\/logo-.*\.svg$/);
  const res = await request.get(href!);
  expect(res.status()).toBe(200);
  expect(res.headers()["content-type"]).toContain("image/svg+xml");
  expect(await res.text()).toContain('d="M14 19 V38 H22 L31 16 L40 48 L45 38 H51"'); // the pulse line

  const brand = page.locator(".topbar .brand").first();
  await expect(brand).toHaveText("LACUNA");
  // Vite may inline the small svg as a data: URL in the CSS (it does on Windows), or link the asset
  const mark = decodeURIComponent(await brand.evaluate((el) => getComputedStyle(el, "::before").backgroundImage));
  expect(mark.includes(href!) || mark.includes("M14 19 V38 H22 L31 16 L40 48 L45 38 H51")).toBe(true);
});
