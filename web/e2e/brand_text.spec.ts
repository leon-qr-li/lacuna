import { expect, test, type Page } from "@playwright/test";
import { AI_PORT } from "../playwright.config";

// brand rule (backlog item 28): no screen shows the AI vendor's name, in Chinese or English. Visible
// text plus title / placeholder / aria-label attributes; the AI is called LACUNA.
const VENDOR = /claude|anthropic|sk-ant/i;

async function vendorText(page: Page) {
  return page.evaluate((src) => {
    const re = new RegExp(src, "i");
    const hits: string[] = [];
    if (re.test(document.title)) hits.push(`title: ${document.title}`);
    if (re.test(document.body.innerText)) hits.push(...document.body.innerText.split("\n").filter((l) => re.test(l)));
    for (const el of document.querySelectorAll("[title], [placeholder], [aria-label], [alt]"))
      for (const a of ["title", "placeholder", "aria-label", "alt"]) {
        const v = el.getAttribute(a);
        if (v && re.test(v)) hits.push(`${a}: ${v}`);
      }
    return hits;
  }, VENDOR.source);
}

async function sweep(page: Page, screens: string[]) {
  const problems: string[] = [];
  for (const lang of ["zh", "en"]) {
    await page.goto("/#/settings");
    await page.evaluate((l) => localStorage.setItem("lacuna.lang", l), lang);
    for (const s of screens) {
      await page.goto(s);
      await page.reload();
      await page.waitForLoadState("networkidle");
      await expect(page.locator(".topbar").first()).toBeVisible();
      problems.push(...(await vendorText(page)).map((h) => `${lang} ${s}: ${h}`));
    }
  }
  await page.evaluate(() => localStorage.removeItem("lacuna.lang"));
  return problems;
}

test("no screen names the AI vendor (zh + en)", async ({ page }) => {
  test.setTimeout(180_000);
  await page.goto("/");
  await expect(page).toHaveURL(/#\/ep\/.+\/listen/, { timeout: 20_000 });
  const ep = /#\/ep\/([^/]+)/.exec(page.url())![1];
  // every episode tab and page (new tabs / pages: add them here)
  const tabs = ["listen", "review", "lessons", "levels", "music", "export", "publish", "ximalaya", "poster", "upload"];
  const screens = ["#/", ...tabs.map((m) => `#/ep/${ep}/${m}`), "#/learning", "#/library", "#/archive", "#/settings", "#/settings/edit", "#/settings/projects", "#/settings/ai"];
  expect(await sweep(page, screens)).toEqual([]);
});

test.describe("with the AI connected", () => {
  test.use({ baseURL: `http://127.0.0.1:${AI_PORT}` });
  test("the AI producer is LACUNA (badge, tooltip, chat)", async ({ page }) => {
    test.setTimeout(120_000);
    await page.goto("/");
    await expect(page).toHaveURL(/#\/ep\/.+\/listen/, { timeout: 20_000 });
    const ep = /#\/ep\/([^/]+)/.exec(page.url())![1];
    await expect(page.getByTestId("editor-badge")).toHaveText("LACUNA");
    expect(await sweep(page, [`#/ep/${ep}/listen`, `#/ep/${ep}/review`])).toEqual([]);
  });
});
