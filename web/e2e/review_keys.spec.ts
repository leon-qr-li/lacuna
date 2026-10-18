import { expect, test } from "@playwright/test";

// review shortcuts (Space, ← →, K, R, ?) and the progress chip in the dock; AI first-cut server
test.use({ baseURL: "http://127.0.0.1:8798" });

test("review shortcuts: arrows move, K keeps, R restores, ? shows the card, typing is ignored", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: /审阅改动/ }).click();
  const items = page.getByTestId("review-list").locator(".ritem");
  const chip = page.getByTestId("dock-progress");
  // other specs share this backend (a chat edit may add one), so count from what is there now
  await expect(chip).toHaveText(/^已过目 \d+ \/ \d+$/);
  const [d0, n] = ((await chip.textContent()) ?? "").match(/\d+/g)!.map(Number);
  await expect(items).toHaveCount(n);
  const at = (d: number) => `已过目 ${d0 + d} / ${n}`;
  await items.first().click();
  await expect(page.getByRole("button", { name: "保留这个删除" })).toBeVisible();
  await expect(items.first()).toHaveAttribute("aria-current", "true");

  // ← → move between edits without deciding
  await page.keyboard.press("ArrowRight");
  await expect(items.nth(1)).toHaveAttribute("aria-current", "true");
  await page.keyboard.press("ArrowLeft");
  await expect(items.first()).toHaveAttribute("aria-current", "true");
  await expect(chip).toHaveText(at(0));

  // K keeps the cut and moves on; the chip and the side panel count together
  await page.keyboard.press("k");
  await expect(page.locator(".toast")).toHaveText("已保留");
  await expect(items.first()).not.toHaveAttribute("aria-current", "true");
  await expect(chip).toHaveText(at(1));
  await expect(page.getByTestId("review-progress")).toContainText(at(1));

  // keys typed into the "adjust in a sentence" box are text, not shortcuts
  const box = page.getByPlaceholder("或者直接说：恢复这处 / 停顿短一点");
  await box.click();
  await page.keyboard.type("kr ");
  await expect(box).toHaveValue("kr ");
  await expect(chip).toHaveText(at(1));
  await box.fill("");
  await box.blur();

  // R restores the original words and moves on
  await items.nth(1).click();
  await expect(page.getByRole("button", { name: "保留这个删除" })).toBeVisible();
  await page.keyboard.press("r");
  await expect(page.locator(".toast")).toHaveText("已恢复原话");
  await expect(chip).toHaveText(at(2));

  // ? opens and closes the shortcut card; the ? button does the same
  await page.keyboard.press("?");
  await expect(page.getByTestId("review-shortcuts")).toContainText("上一处 / 下一处");
  await page.keyboard.press("?");
  await expect(page.getByTestId("review-shortcuts")).toHaveCount(0);
  await page.getByRole("button", { name: "快捷键" }).click();
  await expect(page.getByTestId("review-shortcuts")).toBeVisible();

  // leave the shared backend as we found it
  await page.getByRole("button", { name: "撤销" }).click();
  await expect(chip).toHaveText(at(1));
  await page.getByRole("button", { name: "撤销" }).click();
  await expect(chip).toHaveText(at(0));
});
