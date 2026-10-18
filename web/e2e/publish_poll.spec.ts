import { expect, test } from "@playwright/test";

// full scan 2026-10-18: while a publish pack is being written the page polls every 0.8 s. An answer
// still on its way when Leon left the page used to start a new polling chain that never stopped
// (and could show the previous episode's pack after switching). The job is faked by rewriting
// the server's answer, so the AI workspace is not changed.
test.use({ baseURL: "http://127.0.0.1:8798" });

test("leaving 发布资料 while it polls stops the polling", async ({ page }) => {
  let gets = 0;
  await page.route(/\/api\/episodes\/[^/]+\/publish$/, async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    gets++;
    const res = await route.fetch();
    const body = await res.json();
    body.job = { state: "running", stage: "writing", started: Date.now() / 1000 };
    await new Promise((r) => setTimeout(r, 1200)); // the answer is slow: still on its way when we leave
    await route.fulfill({ response: res, json: body });
  });
  await page.goto("/");
  await expect(page).toHaveURL(/#\/ep\/.+\/listen/);
  await page.getByRole("link", { name: "发布", exact: true }).click();
  await expect(page.getByTestId("publish-running")).toBeVisible();
  await expect.poll(() => gets, { timeout: 10_000 }).toBeGreaterThanOrEqual(2); // polling
  await page.getByRole("link", { name: "整集试听", exact: true }).click();
  await expect(page).toHaveURL(/\/listen$/);
  const left = gets;
  await page.waitForTimeout(4000);
  expect(gets - left).toBeLessThanOrEqual(1); // at most the one already on its way
  await page.unroute(/\/api\/episodes\/[^/]+\/publish$/);
});
