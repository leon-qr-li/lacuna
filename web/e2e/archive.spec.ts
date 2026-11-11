import { expect, test } from "@playwright/test";
import { scan } from "./contrast-scan";

// 首检 #3 on the default server (one demo episode): archive → undo, archive → 已归档 → restore.
// Nothing is deleted here (the other specs share this episode); deleting is in import.spec.ts.
const SHOTS = process.env.ARCHIVE_SHOTS; // folder for review screenshots (optional)

// whatever happens, leave the shared server with nothing archived
test.afterEach(async ({ request }) => {
  for (const e of (await (await request.get("/api/archive")).json()).episodes as { id: string }[])
    await request.post(`/api/episodes/${encodeURIComponent(e.id)}/restore`);
});

for (const theme of ["light", "dark"] as const) {
  test(`archive and restore an episode; buttons and the delete dialog readable (${theme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme });
    await page.goto("/#/");
    await page.evaluate((t) => localStorage.setItem("lacuna.theme", t), theme);
    await page.reload();
    const cards = page.getByTestId("episode");
    await expect(cards).toHaveCount(1);
    const title = (await cards.locator("strong").innerText()).trim();
    await expect(page.getByTestId("archived-link")).toHaveCount(0);

    // archive, then undo from the toast
    await cards.getByRole("button", { name: `归档「${title}」` }).click();
    await expect(cards).toHaveCount(0);
    const toast = page.getByRole("status").filter({ hasText: "已归档" });
    await expect(toast).toBeVisible();
    expect((await scan(page)).bad).toEqual([]);
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/home_toast_${theme}.png` });
    await toast.getByRole("button", { name: "撤销" }).click();
    await expect(cards).toHaveCount(1);

    // archive again → 已归档 page → restore
    await cards.getByRole("button", { name: `归档「${title}」` }).click();
    await expect(page.getByTestId("archived-link")).toHaveText("已归档 · 1");
    expect((await scan(page)).bad).toEqual([]);
    await page.getByTestId("archived-link").click();
    await expect(page.getByRole("heading", { level: 1, name: "已归档" })).toBeVisible();
    const row = page.getByTestId("episode");
    await expect(row).toHaveCount(1);
    await expect(row).toContainText("归档于");
    expect((await scan(page)).bad).toEqual([]);
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/archive_${theme}.png` });

    // the delete dialog is the app's shared one (features/dialog); Esc closes it
    await row.getByRole("button", { name: "永久删除" }).click();
    const dlg = page.getByRole("alertdialog", { name: `永久删除「${title}」？` });
    await expect(dlg).toBeVisible();
    await expect(dlg).toContainText("学到的习惯和规则都会保留");
    await page.waitForTimeout(400);                    // the dialog fades in
    expect((await scan(page)).bad).toEqual([]);
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/delete_dialog_${theme}.png` });
    await page.keyboard.press("Escape");
    await expect(dlg).toHaveCount(0);

    await row.getByRole("button", { name: "恢复" }).click();
    await expect(page.getByRole("status")).toContainText("已恢复到剧集列表");
    await expect(page.getByTestId("archive-empty")).toBeVisible();
    await page.locator(".topbar").getByRole("link", { name: "首页", exact: true }).click();
    await expect(cards).toHaveCount(1);
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/home_${theme}.png` });
  });
}
