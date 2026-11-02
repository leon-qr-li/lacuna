import { expect, test } from "@playwright/test";
import { scan } from "./contrast-scan";

// 改名 (features/episode-name, Leon 2026-11-02): from the pencil in the episode's top bar, and from 「改名」 on
// the home card (the in-app dialog, also on a phone). Default server (one episode); the name is put back after.
let original = "";
let id = "";
test.beforeEach(async ({ request }) => {
  const ep = (await (await request.get("/api/episodes")).json()).episodes[0] as { id: string; title: string };
  id = ep.id;
  original = (await (await request.get(`/api/episodes/${encodeURIComponent(id)}/name`)).json()).name;
});
test.afterEach(async ({ request }) => {
  await request.put(`/api/episodes/${encodeURIComponent(id)}/name`, { data: { name: original } });
});

for (const theme of ["light", "dark"] as const) {
  test(`rename from the top bar (${theme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme });
    await page.goto(`/#/ep/${encodeURIComponent(id)}/listen`);
    await page.evaluate((t) => localStorage.setItem("lacuna.theme", t), theme);
    await page.reload();
    const title = page.getByTestId("episode-title");
    await expect(title).toHaveText(original);
    await page.getByTestId("title-pen").click();
    const input = page.getByTestId("title-input");
    await expect(input).toHaveValue(original);
    await expect(input).toBeFocused();
    expect((await scan(page)).bad).toEqual([]);
    // Esc cancels, nothing changes
    await input.fill("不要这个");
    await input.press("Escape");
    await expect(title).toHaveText(original);
    // Enter saves
    await page.getByTestId("title-pen").click();
    await page.getByTestId("title-input").fill("顶栏改的名字");
    await page.getByTestId("title-input").press("Enter");
    await expect(page.getByTestId("episode-title")).toHaveText("顶栏改的名字");
    await page.reload();
    await expect(page.getByTestId("episode-title")).toHaveText("顶栏改的名字");
    // typing a space in the field types it (the player's shortcut stays out)
    await page.getByTestId("title-pen").click();
    await page.getByTestId("title-input").press("End");
    await page.getByTestId("title-input").pressSequentially(" 二");
    await page.getByTestId("title-save").click();
    await expect(page.getByTestId("episode-title")).toHaveText("顶栏改的名字 二");
  });
}

test("rename from the home card, and an unnamed episode says so", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 }); // a phone
  await page.goto("/#/");
  const card = page.locator(`[data-testid="episode"][data-id="${id}"]`);
  await expect(card).toContainText(original);
  await card.getByTestId("episode-rename").click();
  const dlg = page.getByTestId("rename-dialog");
  await expect(dlg).toBeVisible();
  await expect(dlg.getByTestId("rename-input")).toHaveValue(original);
  expect((await scan(page)).bad).toEqual([]);
  const box = await dlg.boundingBox();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(390);
  await dlg.getByTestId("rename-input").fill("手机上改的");
  await dlg.getByTestId("rename-save").click();
  await expect(dlg).toBeHidden();
  await expect(card).toContainText("手机上改的");
  // empty: back to only the number, the card says it has no name yet
  await card.getByTestId("episode-rename").click();
  await page.getByTestId("rename-input").fill("");
  await expect(page.getByTestId("rename-dialog")).toContainText("空着就先只用编号");
  await page.getByTestId("rename-save").click();
  await expect(card.getByTestId("episode-unnamed")).toHaveText(/还没起名/);
  await expect(card.locator("strong")).toHaveText(id);
  // Esc closes without saving
  await card.getByTestId("episode-rename").click();
  await page.getByTestId("rename-input").fill("不保存");
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("rename-dialog")).toBeHidden();
  await expect(card.locator("strong")).toHaveText(id);
});
