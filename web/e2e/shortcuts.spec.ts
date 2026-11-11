import { expect, test, type Page } from "@playwright/test";

// 自定义快捷键 (docs/decisions/2026-11-02-custom-shortcuts.md): 设置 → 快捷键 records a new key, asks before taking
// one another action uses, refuses the browser's keys, restores defaults; the pages use the person's own keys and
// the "?" cards show them with a link here.
const EP = encodeURIComponent("EP_TEST_合成");
const gaps = async (page: Page) => ((await (await page.request.get(`/api/episodes/${EP}/gaps`)).json()).gaps as { id: string }[]);

test.afterEach(async ({ request }) => {
  await request.put("/api/shortcuts", { data: { keys: {} } }); // the shared server back to the defaults
  for (const g of (await (await request.get(`/api/episodes/${EP}/gaps`)).json()).gaps) await request.delete(`/api/episodes/${EP}/gaps/${g.id}`);
});

for (const theme of ["light", "dark"] as const)
  test(`settings: record, clash, refuse, restore (${theme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme });
    await page.goto("/#/settings");
    await page.getByTestId("settings-nav-keys").click();
    const card = page.getByTestId("shortcuts-card");
    await expect(card).toBeVisible();
    await expect(page.getByTestId("shortcut-gap-0")).toHaveText("Shift+G");
    await expect(page.getByTestId("shortcut-cut-0")).toHaveText("Ctrl+X");
    await expect(page.getByTestId("shortcut-cut-1")).toHaveText("Delete");
    await expect(page.getByTestId("shortcut-gap-reset")).toBeHidden();

    // record H for 加入间隙: saved, ↺ shows, it survives a reload
    await page.getByTestId("shortcut-gap-0").click();
    await expect(page.getByTestId("shortcut-recording")).toBeVisible();
    await page.keyboard.press("h");
    await expect(page.getByTestId("shortcut-gap-0")).toHaveText("H");
    await expect(page.getByTestId("shortcut-gap-reset")).toBeVisible();
    await page.reload();
    await expect(page.getByTestId("shortcut-gap-0")).toHaveText("H");

    // a key used on the same page: asked first; 取消 keeps both as they were
    const box = await card.boundingBox();
    await page.getByTestId("shortcut-find-0").click();
    await page.keyboard.press("h");
    const clash = page.getByTestId("shortcut-conflict");
    await expect(clash).toContainText("已经用在「剪辑 · 在播放头加入间隙」");
    expect((await card.boundingBox())!.height).toBe(box!.height); // floats: nothing moved
    await page.getByTestId("shortcut-conflict-cancel").click();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("shortcut-find-0")).toHaveText("Ctrl+F");
    // 改用在这里: 搜索 gets H, 加入间隙 has no key left
    await page.getByTestId("shortcut-find-0").click();
    await page.keyboard.press("h");
    await page.getByTestId("shortcut-take").click();
    await expect(page.getByTestId("shortcut-find-0")).toHaveText("H");
    await expect(page.getByTestId("shortcut-gap-0")).toHaveText("未设置");
    // a review-page key on 试听 is fine: K is 保留 on 审阅 only
    await page.getByTestId("shortcut-gap-0").click();
    await page.keyboard.press("k");
    await expect(page.getByTestId("shortcut-gap-0")).toHaveText("K");

    // the browser's own keys are refused
    await page.getByTestId("shortcut-undo-1").click();
    await page.keyboard.press("F12");
    await expect(page.getByTestId("shortcut-refused")).toContainText("这个键浏览器自己要用");
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("shortcut-refused")).toHaveCount(0);

    // remove a key; then 全部恢复默认 asks in the app's own dialog
    await page.getByTestId("shortcut-keep-1").click();
    await page.getByTestId("shortcut-remove").click();
    await expect(page.getByTestId("shortcut-keep-1")).toHaveText("＋ 再加一个");
    await page.getByTestId("shortcuts-reset-all").click();
    const dlg = page.getByTestId("dialog");
    await expect(dlg).toContainText("你改过的 3 个快捷键会变回默认。");
    await dlg.getByRole("button", { name: "恢复默认" }).click();
    await expect(page.getByTestId("shortcut-gap-0")).toHaveText("Shift+G");
    await expect(page.getByTestId("shortcut-find-0")).toHaveText("Ctrl+F");
    await expect(page.getByTestId("shortcuts-reset-all")).toBeDisabled();
    expect((await (await page.request.get("/api/shortcuts")).json()).keys).toEqual({});
  });

test("settings: English fits", async ({ page, context }) => {
  await context.addCookies([{ name: "lacuna_lang", value: "en", url: "http://127.0.0.1:8799" }]);
  await page.addInitScript(() => localStorage.setItem("lacuna.lang", "en"));
  await page.goto("/#/settings/keys");
  const card = page.getByTestId("shortcuts-card");
  await expect(card).toBeVisible();
  // no row wider than the card
  const w = (await card.boundingBox())!.width;
  for (const r of await card.locator(".sk-row").all()) expect((await r.boundingBox())!.width).toBeLessThanOrEqual(w + 1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
});

test("the pages use the person's keys; the ? card shows them and links here", async ({ page }) => {
  await page.request.put("/api/shortcuts", { data: { keys: { gap: ["H"] } } });
  await page.goto(`/#/ep/${EP}/listen`);
  await expect(page.getByTestId("edit-lanes")).toBeVisible();
  await page.getByTestId("edit-lanes").getByRole("heading", { name: "剪辑时间线" }).click();
  await page.keyboard.press("Shift+G"); // the default no longer
  await page.waitForTimeout(300);
  expect((await gaps(page)).length).toBe(0);
  await page.keyboard.press("h");
  await expect.poll(async () => (await gaps(page)).length).toBe(1);
  await page.getByTestId("ml-help").hover();
  const tip = page.locator("#ml-help-tip");
  await expect(tip).toContainText("右键空白处，或按 H");
  await tip.getByTestId("customize-shortcuts").click();
  await expect(page).toHaveURL(/#\/settings\/keys$/);
  await expect(page.getByTestId("shortcut-gap-0")).toHaveText("H");
});
