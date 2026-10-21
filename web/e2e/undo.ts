import type { Page } from "@playwright/test";

/** Undo / redo by keyboard: the episode top bar has no 撤销 / 重做 buttons (Ctrl+Z / Ctrl+Shift+Z). */
export async function undoKey(page: Page) {
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur?.()); // not while typing
  await page.keyboard.press("Control+z");
}

export async function redoKey(page: Page) {
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur?.());
  await page.keyboard.press("Control+Shift+z");
}
