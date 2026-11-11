import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { IMPORT_PORT } from "../playwright.config";
import { scan } from "./contrast-scan";

// 配乐上传进度条 (Leon 2026-10-31): while a music file uploads, the library shows a bar per file (how much has
// gone, then 「正在读取音频」 while the server reads it); when it is in, the usual 「已加入」 line. Runs on the import
// server (its own library), the upload held back a moment so the bar can be seen.
test.use({ baseURL: `http://127.0.0.1:${IMPORT_PORT}` });
const INBOX = join(dirname(fileURLToPath(import.meta.url)), ".fixtures", "music_inbox");

for (const theme of ["light", "dark"] as const) {
  test(`a music upload shows its progress (${theme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme });
    await page.goto("/#/library");
    await page.evaluate((t) => localStorage.setItem("lacuna.theme", t), theme);
    await page.reload();
    let release: () => void = () => undefined;
    const held = new Promise<void>((r) => (release = r));
    await page.route("**/api/library/upload**", async (route) => {
      await held;
      await route.continue();
    });
    await page.getByLabel("选择音乐文件").first().setInputFiles(join(INBOX, "odyssey_theme.mp3"));
    const meter = page.getByTestId("upload-meter");
    await expect(meter).toBeVisible();
    await expect(meter.getByRole("progressbar")).toHaveAttribute("aria-label", "上传进度：odyssey_theme.mp3");
    expect((await scan(page)).bad).toEqual([]);
    release();
    await expect(page.getByTestId("uploads")).toContainText(/已加入：odyssey_theme\.mp3|跳过：odyssey_theme\.mp3/);
    await expect(meter).toHaveCount(0);
    // leave the library as it was
    for (const a of (await (await page.request.get("/api/library")).json()).assets as { id: string }[])
      await page.request.delete(`/api/library/assets/${a.id}?force=true`);
  });
}
