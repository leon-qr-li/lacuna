import { expect, test } from "@playwright/test";
import { scan } from "./contrast-scan";

// every enabled button (and link styled as one) on every screen has readable text, light and dark:
// WCAG AA 4.5:1 against the nearest solid background (gradient buttons: their text against every
// stop of the gradient). Guards against e.g. a.btn-primary painting navy text on navy.

for (const theme of ["light", "dark"] as const) {
  test(`buttons are readable on every screen (${theme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme });
    await page.goto("/");
    await page.evaluate((t) => localStorage.setItem("lacuna.theme", t), theme);
    await page.reload();
    await expect(page).toHaveURL(/#\/ep\/.+\/listen/);
    const ep = /#\/ep\/([^/]+)/.exec(page.url())![1];
    const api = `/api/episodes/${ep}`;
    // a WAV exists, so the upload page shows its 下载 WAV link-button
    expect((await page.request.post(`${api}/export`, { data: { formats: ["wav"] } })).ok()).toBe(true);
    await expect.poll(async () => (await (await page.request.get(`${api}/export`)).json()).job?.state ?? "none", { timeout: 30_000 }).not.toBe("running");

    const screens = ["#/", `#/ep/${ep}/listen`, `#/ep/${ep}/review`, `#/ep/${ep}/music`, `#/ep/${ep}/export`,
      `#/ep/${ep}/publish`, `#/ep/${ep}/poster`, `#/ep/${ep}/upload`, "#/learning", "#/library", "#/settings"];
    const problems: string[] = [];
    let total = 0;
    for (const s of screens) {
      await page.goto("/" + s);
      await page.waitForLoadState("networkidle");
      await page.waitForTimeout(400);
      const { n, bad } = await scan(page);
      total += n;
      problems.push(...bad.map((b) => `${s}: ${b}`));
    }
    // hovered primary link-button keeps its text color too
    await page.goto(`/#/ep/${ep}/upload`);
    const dl = page.getByRole("link", { name: "下载 WAV" });
    await expect(dl).toBeVisible();
    await dl.hover();
    const hovered = await scan(page);
    problems.push(...hovered.bad.map((b) => `upload (hover): ${b}`));

    expect(total).toBeGreaterThan(30);
    expect(problems).toEqual([]);
  });
}
