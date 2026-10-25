import { expect, test, type Page } from "@playwright/test";

// in-app confirm dialog (features/dialog, backlog item 13) instead of the browser's native box:
// title + message, red confirm for destructive actions, Esc / Cancel / backdrop keep things, Enter
// confirms, readable in light and dark, English too. Exercised on 素材库 → 移出素材库.

function wav(seconds = 1, rate = 8000) {
  const n = seconds * rate, b = Buffer.alloc(44 + n * 2);
  b.write("RIFF", 0); b.writeUInt32LE(36 + n * 2, 4); b.write("WAVEfmt ", 8); b.writeUInt32LE(16, 16);
  b.writeUInt16LE(1, 20); b.writeUInt16LE(1, 22); b.writeUInt32LE(rate, 24); b.writeUInt32LE(rate * 2, 28);
  b.writeUInt16LE(2, 32); b.writeUInt16LE(16, 34); b.write("data", 36); b.writeUInt32LE(n * 2, 40);
  for (let i = 0; i < n; i++) b.writeInt16LE(Math.round(3000 * Math.sin((i / rate) * 2 * Math.PI * 440)), 44 + i * 2);
  return b;
}

async function addAsset(page: Page, name: string) {
  const r = await page.request.post(`/api/library/upload?name=${encodeURIComponent(name)}&kind=other`, {
    headers: { "content-type": "application/octet-stream" }, data: wav(),
  });
  expect(r.ok()).toBe(true);
}

const lum = (rgb: string) => {
  const [r, g, b] = (rgb.match(/[\d.]+/g) ?? []).slice(0, 3).map(Number).map((x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const contrast = (a: string, b: string) => { const [h, l] = [lum(a), lum(b)].sort((x, y) => y - x); return (h + 0.05) / (l + 0.05); };

for (const theme of ["light", "dark"] as const) {
  test(`移出素材库 asks in an in-app dialog (${theme})`, async ({ page }) => {
    const name = `dialog_test_${theme}.wav`;
    await addAsset(page, name);
    await page.goto("/#/library");
    await page.evaluate((th) => localStorage.setItem("lacuna.theme", th), theme);
    await page.reload();
    let native = false;
    page.on("dialog", (d) => { native = true; void d.dismiss(); });
    const row = page.getByTestId("asset-row").filter({ hasText: name });
    const dlg = page.getByRole("alertdialog");

    // Esc keeps the file
    await row.getByRole("button", { name: "移出素材库" }).click();
    await expect(dlg).toBeVisible();
    await expect(dlg.getByRole("heading")).toHaveText("移出素材库");
    await expect(dlg).toContainText(`把「${name}」移出素材库？`);
    const ok = dlg.getByRole("button", { name: "移出", exact: true });
    await expect(ok).toBeFocused();
    // true red, readable text
    const [bg, fg] = await ok.evaluate((el) => [getComputedStyle(el).backgroundColor, getComputedStyle(el).color]);
    const [r, g, b] = (bg.match(/\d+/g) ?? []).map(Number);
    expect(r).toBeGreaterThan(180); expect(g).toBeLessThan(80); expect(b).toBeLessThan(90);
    expect(contrast(bg, fg)).toBeGreaterThanOrEqual(4.5);
    const cancel = dlg.getByRole("button", { name: "取消" });
    const [cbg, cfg] = await cancel.evaluate((el) => [getComputedStyle(el).backgroundColor, getComputedStyle(el).color]);
    expect(contrast(cbg, cfg)).toBeGreaterThanOrEqual(4.5);
    await page.keyboard.press("Escape");
    await expect(dlg).toHaveCount(0);
    await expect(row).toHaveCount(1);

    // Cancel and a click on the backdrop keep it too
    await row.getByRole("button", { name: "移出素材库" }).click();
    await cancel.click();
    await expect(dlg).toHaveCount(0);
    await row.getByRole("button", { name: "移出素材库" }).click();
    await page.mouse.click(5, 5);
    await expect(dlg).toHaveCount(0);
    await expect(row).toHaveCount(1);

    // Tab to 取消 + Enter cancels (Enter presses the focused button); other keys don't reach the
    // page under the dialog (Ctrl+Z would undo an edit there)
    await page.evaluate(() => {
      (window as unknown as { leaked: string[] }).leaked = [];
      window.addEventListener("keydown", (e) => (window as unknown as { leaked: string[] }).leaked.push(e.key));
    });
    await row.getByRole("button", { name: "移出素材库" }).click();
    await page.keyboard.press("Control+z");
    await page.keyboard.press("ArrowRight");
    await page.keyboard.press("k");
    expect(await page.evaluate(() => (window as unknown as { leaked: string[] }).leaked)).toEqual([]);
    await page.keyboard.press("Tab");
    await expect(cancel).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(dlg).toHaveCount(0);
    await expect(row).toHaveCount(1);

    // Enter removes it
    await row.getByRole("button", { name: "移出素材库" }).click();
    await expect(dlg).toBeVisible();
    await page.keyboard.press("Enter");
    await expect(dlg).toHaveCount(0);
    await expect(row).toHaveCount(0);
    expect(native).toBe(false);
  });
}

test("the dialog speaks English in the English interface", async ({ page }) => {
  const name = "dialog_test_en.wav";
  await addAsset(page, name);
  await page.goto("/#/library");
  await page.evaluate(() => localStorage.setItem("lacuna.lang", "en"));
  await page.reload();
  const row = page.getByTestId("asset-row").filter({ hasText: name });
  await row.getByRole("button", { name: "Remove from library" }).click();
  const dlg = page.getByRole("alertdialog");
  await expect(dlg.getByRole("button", { name: "Cancel" })).toBeVisible();
  await dlg.getByRole("button", { name: "Remove", exact: true }).click();
  await expect(row).toHaveCount(0);
  await page.evaluate(() => localStorage.removeItem("lacuna.lang"));
});

// batch 8 regression: a file an episode's music plays is named in a second question before it goes
test("移出素材库: a file an episode still uses asks once more, naming the episode", async ({ page }) => {
  const name = "dialog_in_use.wav";
  await addAsset(page, name);
  let tries = 0;
  await page.route(/\/api\/library\/assets\/[^/]+$/, async (route) => {
    if (route.request().method() !== "DELETE") return route.fallback();
    tries++;
    if (!route.request().url().includes("force=true"))
      return route.fulfill({ status: 409, json: { detail: `「${name}」还用在 EP001 的配乐里。移出后这些剧集的配乐就没有它了，导出时也不会有。` } });
    return route.fallback();
  });
  await page.goto("/#/library");
  const row = page.getByTestId("asset-row").filter({ hasText: name });
  const dlg = page.getByRole("alertdialog");
  await row.getByRole("button", { name: "移出素材库" }).click();
  await dlg.getByRole("button", { name: "移出", exact: true }).click();
  await expect(dlg).toContainText("还用在 EP001 的配乐里");
  await dlg.getByRole("button", { name: "取消" }).click();
  await expect(row).toHaveCount(1);                      // kept
  await row.getByRole("button", { name: "移出素材库" }).click();
  await dlg.getByRole("button", { name: "移出", exact: true }).click();
  await dlg.getByRole("button", { name: "仍然移出" }).click();
  await expect(row).toHaveCount(0);
  expect(tries).toBe(3);                                // asked, asked, then removed with force
  await page.unroute(/\/api\/library\/assets\/[^/]+$/);
});
