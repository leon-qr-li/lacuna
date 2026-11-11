import { expect, test, type Page } from "@playwright/test";
import { SCOPES_PORT } from "../playwright.config";
import { undoKey } from "./undo";

// 去掉 um / uh (decision english-fillers): an English episode shows how many um / uh are still heard on 逐字稿剪辑;
// the panel takes them all out (or one host's) in one undoable step. Runs on the scopes server, which holds an
// English copy of the synthetic episode (tests/app/synth_en.py).
test.use({ baseURL: `http://127.0.0.1:${SCOPES_PORT}` });
const EP = "EP_TEST_English";

async function open(page: Page, ep = EP) {
  await page.goto(`/#/ep/${encodeURIComponent(ep)}/listen`);
  await expect(page.getByTestId("transcript-edit")).toBeVisible();
}

test.describe.serial("um / uh", () => {
  test("a Chinese episode has no um / uh chip", async ({ page }) => {
    await open(page, "EP_TEST_合成");
    await expect(page.getByTestId("ml-tx").locator(".ml-w").first()).toBeVisible();
    await expect(page.getByTestId("fillers-btn")).toHaveCount(0);
  });

  test("the um / uh the recogniser dropped show in the transcript", async ({ page }) => {
    await open(page);
    await expect(page.getByTestId("ml-tx").locator(".ml-w", { hasText: /^Um,$/ })).toHaveCount(1);
    await expect(page.getByTestId("fillers-btn")).toContainText("4");
  });

  test("one host only, then all; one undo brings them back; a struck one restores alone", async ({ page }) => {
    await open(page);
    await page.getByTestId("fillers-btn").click();
    const pop = page.getByTestId("fillers-pop");
    await expect(pop).toContainText("还听得到 4 个，已剪掉 1 个");
    await pop.getByRole("checkbox").first().uncheck(); // leave Leon's in
    await expect(pop.getByTestId("fillers-cut")).toHaveText("去掉 1 个");
    await pop.getByTestId("fillers-cut").click();
    await expect(page.locator(".toast")).toContainText("已去掉 1 个 um / uh，Ctrl+Z 可撤销");
    await expect(pop).toHaveCount(0);
    await expect(page.getByTestId("fillers-btn")).toContainText("3");

    await page.getByTestId("fillers-btn").click();
    await page.getByTestId("fillers-cut").click();
    await expect(page.locator(".toast")).toContainText("已去掉 3 个");
    await expect(page.getByTestId("fillers-btn")).toContainText("0");
    await page.getByTestId("fillers-btn").click();
    await expect(page.getByTestId("fillers-pop")).toContainText("都剪掉了（5 个）");
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("fillers-pop")).toHaveCount(0);

    // the first word, "Um,", is struck through; a click brings back only it
    const struck = page.getByTestId("ml-tx").locator("s.ml-gone", { hasText: /^Um,$/ });
    await expect(struck).toHaveCount(1);
    await struck.click();
    await expect(page.getByTestId("fillers-btn")).toContainText("1");

    await undoKey(page); // the restore
    await expect(page.locator(".toast")).toContainText("已撤销：恢复");
    await undoKey(page); // the three
    await expect(page.locator(".toast")).toContainText("已撤销：去掉 um / uh（3 处）");
    await expect(page.getByTestId("fillers-btn")).toContainText("3");
    await undoKey(page);
    await expect(page.getByTestId("fillers-btn")).toContainText("4");
  });

  test("听下一个 jumps to the next um / uh and plays", async ({ page }) => {
    await open(page);
    await page.getByTestId("fillers-btn").click();
    await page.getByTestId("fillers-hear").click();
    await expect(page.getByTestId("play")).toHaveAttribute("aria-label", "暂停");
    await page.getByTestId("play").click();
  });
});
