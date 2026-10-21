import { expect, test } from "@playwright/test";
import { scan } from "./contrast-scan";

// 专辑 (design A) on the default server (one demo episode): make an album from 剧集, the one-album
// view, move the episode out and back, the album page, then delete the album (the episode stays).
const SHOTS = process.env.ALBUM_SHOTS; // folder for review screenshots (optional)

// whatever happens, leave the shared server with no albums
const clean = async ({ request }: { request: import("@playwright/test").APIRequestContext }) => {
  for (const a of (await (await request.get("/api/albums")).json()).albums as { id: string }[])
    await request.delete(`/api/albums/${encodeURIComponent(a.id)}`);
};
test.beforeEach(clean);
test.afterEach(clean);

for (const theme of ["light", "dark"] as const) {
  test(`make an album, move the episode, delete the album (${theme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme });
    await page.goto("/#/");
    await page.evaluate((t) => localStorage.setItem("lacuna.theme", t), theme);
    await page.reload();
    const card = page.getByTestId("episode");
    await expect(card).toHaveCount(1);
    const title = (await card.locator("strong").innerText()).trim();
    // no albums yet: today's list, and a small 「＋ 新专辑」
    await expect(page.getByTestId("album-row")).toHaveCount(0);
    await expect(card.getByTestId("album-move")).toHaveCount(0);

    await page.getByTestId("album-new").click();
    const dlg = page.getByTestId("album-dialog");
    await expect(dlg).toBeVisible();
    await expect(dlg.getByRole("button", { name: "建好专辑" })).toBeDisabled();
    await dlg.getByTestId("album-name").fill("九十年代港片");
    await dlg.getByRole("checkbox").check();
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/album-dialog-${theme}.png` });
    expect((await scan(page)).bad).toEqual([]);
    await dlg.getByTestId("album-save").click();

    // straight onto the new album's page
    await expect(page).toHaveURL(/#\/album\//);
    const strip = page.getByTestId("album-strip");
    await expect(strip).toContainText("九十年代港片");
    await expect(strip).toContainText("1 集");
    await expect(strip).toContainText("默认片头");
    await expect(page.getByTestId("album-page").getByTestId("episode")).toHaveCount(1);
    await expect(page.getByTestId("album-shelf")).toContainText("还没有只给这个专辑用的素材");
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/album-page-${theme}.png`, fullPage: true });
    expect((await scan(page)).bad).toEqual([]);

    // 剧集 with one album holding every episode: no extra click, the strip and the episode right there
    await page.goto("/#/");
    await expect(page.getByTestId("album-strip")).toContainText("九十年代港片");
    await expect(page.getByTestId("album-row")).toHaveCount(0);
    await expect(card).toHaveCount(1);

    // the card's actions (移到专辑 / 归档) sit in a row under the text, never over the title
    const tb = (await card.locator(".ep-body > strong").boundingBox())!;
    for (const b of [card.getByTestId("album-move"), card.locator(".ep-archive")]) {
      const ab = (await b.boundingBox())!;
      expect(ab.y).toBeGreaterThanOrEqual(tb.y + tb.height);
    }

    // move it out: the album shows as a cover, the episode under 不在专辑里
    await card.getByTestId("album-move").click();
    await page.getByTestId("album-menu").getByRole("menuitemradio", { name: "不在专辑里" }).click();
    await expect(page.getByTestId("album-row")).toBeVisible();
    await expect(page.getByTestId("album-tile")).toContainText("0 集");
    await expect(page.getByRole("heading", { name: "不在专辑里" })).toBeVisible();
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/album-home-${theme}.png`, fullPage: true });
    expect((await scan(page)).bad).toEqual([]);

    // and back in
    await card.getByTestId("album-move").click();
    await expect(page.getByTestId("album-menu").getByRole("menuitemradio", { name: "不在专辑里" })).toHaveAttribute("aria-checked", "true");
    await page.getByTestId("album-menu").getByRole("menuitemradio", { name: "九十年代港片" }).click();
    await expect(page.getByTestId("album-strip")).toBeVisible();

    // the import form offers the album, already picked
    await page.getByRole("button", { name: "导入新一集" }).click();
    const pick = page.getByTestId("import-album");
    await expect(pick).toBeVisible();
    await expect(pick.locator("option:checked")).toHaveText("九十年代港片");
    await page.getByRole("button", { name: "取消" }).click();

    // delete it from 专辑设置: asked first, then the episode is still there, in no album
    await page.getByTestId("album-settings").click();
    await page.getByTestId("album-dialog").getByRole("button", { name: "删除专辑" }).click();
    const ask = page.getByRole("alertdialog");
    await expect(ask).toContainText("里面的剧集不会删");
    await ask.getByRole("button", { name: "删除专辑" }).click();
    await expect(page.getByTestId("album-strip")).toHaveCount(0);
    await expect(page.getByTestId("album-row")).toHaveCount(0);
    await expect(card).toHaveCount(1);
    await expect(card.locator("strong")).toHaveText(title);
  });
}

test("albums in English", async ({ page }) => {
  await page.goto("/#/");
  await page.evaluate(() => localStorage.setItem("lacuna.lang", "en"));
  await page.reload();
  await page.getByTestId("album-new").click();
  const dlg = page.getByTestId("album-dialog");
  await expect(dlg.getByRole("heading")).toHaveText("New album");
  await dlg.getByTestId("album-name").fill("Nineties");
  await dlg.getByTestId("album-save").click();
  await expect(page.getByTestId("album-strip")).toContainText("Default intro");
  await expect(page.getByTestId("album-shelf")).toContainText("Media for this album");
  await page.evaluate(() => localStorage.removeItem("lacuna.lang"));
});
