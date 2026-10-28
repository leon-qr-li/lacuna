import { expect, test, type Browser, type Page } from "@playwright/test";

// No show at all (Leon 2026-10-28: he deleted his last show and the sample, and the home page said
// 「你还没有节目……」 with 重试): the app opens straight on making the first show, readable in zh + en and in
// both themes, and the new show's 剧集 then asks for its hosts.
const PW = "correct horse battery";

test.describe.configure({ mode: "serial" });
test.beforeAll(async ({ request }) => {
  await request.post("/api/auth/_test/reset?skip_setup=false");
});
test.afterAll(async ({ request }) => {
  await request.post("/api/auth/_test/reset?skip_setup=true");
});

/** An invited beta user, signed in (Leon's own main show stays as the other specs expect it). */
async function betaUser(browser: Browser): Promise<Page> {
  const lp = await (await browser.newContext()).newPage();
  expect((await lp.request.post("/api/auth/register", { data: { email: "leon@example.com", password: PW } })).ok()).toBeTruthy();
  const inv = await (await lp.request.post("/api/auth/invites", { data: { email: "solo@example.com", plan: "pro" } })).json();
  const page = await (await browser.newContext()).newPage();
  expect((await page.request.post("/api/auth/register", { data: { invite: inv.link.split("/").at(-1), password: PW } })).ok()).toBeTruthy();
  await page.goto("/"); // signing up signed them in
  await expect(page.locator(".topbar")).toBeVisible();
  return page;
}

/** Leaves the signed-in person in no show: their own one archived and deleted (the sample kept it from being
 *  the only one), then the sample dropped. */
async function noShows(page: Page) {
  const r = page.request;
  expect((await r.post("/api/onboarding/sample", { data: { lang: "zh" } })).ok()).toBeTruthy();
  const own = (await (await r.get("/api/spaces")).json()).mine.find((m: { sample: boolean }) => !m.sample);
  expect((await r.post(`/api/spaces/${own.id}/archive`, { data: { archived: true } })).ok()).toBeTruthy();
  expect((await r.delete(`/api/spaces/${own.id}`, { data: { confirm: own.name } })).ok()).toBeTruthy();
  expect((await r.delete("/api/onboarding/sample")).ok()).toBeTruthy();
  expect((await (await r.get("/api/spaces")).json()).mine).toEqual([]);
}

test("in no show, the app opens on making the first one", async ({ browser }) => {
  const page = await betaUser(browser);
  await noShows(page);

  for (const [lng, theme, title] of [
    ["zh", "light", "建你的第一个节目"],
    ["zh", "dark", "建你的第一个节目"],
    ["en", "light", "Create your first show"],
    ["en", "dark", "Create your first show"],
  ] as const) {
    await page.evaluate(([l, th]) => {
      localStorage.setItem("lacuna.lang", l);
      localStorage.setItem("lacuna.theme", th);
    }, [lng, theme]);
    await page.goto("/#/library"); // any show page lands here too
    await page.reload();
    const card = page.getByTestId("first-show");
    await expect(card.getByRole("heading")).toHaveText(title);
    await expect(page.getByTestId("error-state")).toHaveCount(0);
    // nothing spills out of the card
    for (const el of await card.locator("h1, p, label, button").all())
      expect(await el.evaluate((n) => n.scrollWidth <= n.clientWidth + 1)).toBeTruthy();
  }
  await page.evaluate(() => {
    localStorage.setItem("lacuna.lang", "zh");
    localStorage.removeItem("lacuna.theme");
  });
  await page.goto("/");
  await page.reload();
  // 设置 still opens (account, sign out)
  await page.goto("/#/settings");
  await expect(page.getByTestId("first-show")).toHaveCount(0);
  await page.goto("/#/");

  await expect(page.getByTestId("first-show-create")).toBeDisabled();
  await page.getByTestId("first-show-name").fill("周末电影院");
  await page.getByTestId("first-show-create").click();
  // the new show: its 剧集 asks for the language and hosts first
  await expect(page.getByTestId("project-menu")).toHaveText(/周末电影院/, { timeout: 20_000 });
  await expect(page.getByTestId("first-show")).toHaveCount(0);
  const sp = await (await page.request.get("/api/spaces")).json();
  expect(sp.current.name).toBe("周末电影院");
});
