import { expect, test } from "@playwright/test";
import { scan } from "./contrast-scan";

// 专辑设置 → 剧集命名 (Leon 2026-10-31): presets (编号 + 空格 + 名称 first) and a custom format, each showing the
// title it makes; the import form says what the new episode will be called; existing episodes are renamed only
// when asked, after a question listing before → after. Default server (one episode).
const clean = async ({ request }: { request: import("@playwright/test").APIRequestContext }) => {
  for (const a of (await (await request.get("/api/albums")).json()).albums as { id: string }[])
    await request.delete(`/api/albums/${encodeURIComponent(a.id)}`);
};
test.beforeEach(clean);
test.afterEach(clean);

for (const theme of ["light", "dark"] as const) {
  test(`pick an episode naming for an album (${theme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme });
    await page.goto("/#/");
    await page.evaluate((t) => localStorage.setItem("lacuna.theme", t), theme);
    const eps = (await (await page.request.get("/api/episodes")).json()).episodes as { id: string; title: string }[];
    const ep = eps[0];
    const aid = (await (await page.request.post("/api/albums", { data: { name: "港片", episodes: [ep.id] } })).json()).created as string;
    await page.goto(`/#/album/${aid}`);
    await page.getByTestId("album-settings").click();
    const dlg = page.getByTestId("album-dialog");
    const field = dlg.getByTestId("album-naming");
    // an album made before keeps its titles as typed until a format is picked
    await expect(field.getByTestId("naming-none")).toBeChecked();
    await expect(field).toContainText("编号 + 空格 + 名称");
    await field.getByTestId("naming-dot").check();
    await expect(field.locator(".nm-opt.is-on")).toContainText(`${ep.id} · 奥本海默`);
    await field.getByTestId("naming-custom").check();
    await field.getByTestId("naming-before").fill("【");
    await field.getByTestId("naming-between").fill("】");
    await expect(field.getByTestId("naming-preview")).toHaveText(`会叫：【${ep.id}】奥本海默`);
    expect((await scan(page)).bad).toEqual([]);
    await field.getByTestId("naming-space").check();

    // existing episodes: only after the question, which lists the new title
    await dlg.getByTestId("naming-rename").click();
    const ask = page.getByRole("alertdialog").filter({ hasText: "改成新格式" });
    await expect(ask).toContainText(`→ ${ep.id}`);
    await ask.getByRole("button", { name: "取消" }).click();
    expect((await (await page.request.get(`/api/episodes/${encodeURIComponent(ep.id)}`)).json()).title).toBe(ep.title);

    await dlg.getByTestId("album-save").click();
    await expect(dlg).toHaveCount(0);
    const saved = (await (await page.request.get("/api/albums")).json()).albums.find((a: { id: string }) => a.id === aid);
    expect(saved.naming).toEqual({ preset: "space" });
    // the import form on the album page says what the next episode will be called
    await page.getByRole("button", { name: "导入新一集" }).click();
    const id = await page.getByTestId("import-id").inputValue();
    await page.getByTestId("import-title").fill("奥本海默");
    await expect(page.getByTestId("import-naming")).toHaveText(`这一集会叫：${id} 奥本海默`);
    expect((await scan(page)).bad).toEqual([]);
  });
}
