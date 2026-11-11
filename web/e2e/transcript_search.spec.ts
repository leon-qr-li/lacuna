import { expect, test } from "@playwright/test";
import { scan } from "./contrast-scan";

// 逐字稿搜索 in 整集试听 (lacuna_app/transcript_search.py, Leon 2026-10-31 direction A, small): a pill on 逐字稿剪辑;
// typing lights every place up in the transcript and on the ruler, Enter jumps to the next after the playhead,
// Ctrl+F puts the cursor in it, Esc clears. Read-only, so it runs on the shared episode.
const EP = "EP_TEST_合成";

for (const theme of ["light", "dark"] as const) {
  test(`search the transcript and jump from place to place (${theme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme });
    await page.goto("/#/");
    await page.evaluate((t) => localStorage.setItem("lacuna.theme", t), theme);
    await page.goto(`/#/ep/${encodeURIComponent(EP)}/listen`);
    const box = page.getByTestId("ts");
    await expect(box).toBeVisible();
    // small: no wider than the chips around it
    expect((await box.boundingBox())!.width).toBeLessThan(140);
    await page.getByTestId("transcript-edit").screenshot({ path: `test-results/transcript-search-idle-${theme}.png` });
    const hits = (await (await page.request.get(`/api/episodes/${encodeURIComponent(EP)}/transcript/search?q=${encodeURIComponent("电影")}`)).json()).hits;
    expect(hits.length).toBeGreaterThan(3);

    await page.keyboard.press("Control+f");
    await expect(page.getByTestId("ts-in")).toBeFocused();
    await page.keyboard.type("电影");
    await expect(page.getByTestId("ts-n")).toHaveText(`${hits.length} 处`);
    expect((await box.boundingBox())!.width).toBeLessThan(260);
    await expect(page.locator(".ml-w.ts-hit").first()).toBeVisible();
    await expect(page.getByTestId("ts-tick").first()).toBeVisible();

    const audio = page.getByTestId("main-audio");
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("ts-n")).toHaveText(`1/${hits.length}`);
    await expect.poll(() => audio.evaluate((el: HTMLAudioElement) => el.currentTime)).toBeCloseTo(hits[0].start, 1);
    await expect(page.locator(".ml-w.ts-cur").first()).toBeVisible();
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("ts-n")).toHaveText(`2/${hits.length}`);
    await expect.poll(() => audio.evaluate((el: HTMLAudioElement) => el.currentTime)).toBeCloseTo(hits[1].start, 1);
    expect(await audio.evaluate((el: HTMLAudioElement) => el.paused)).toBe(true); // a jump keeps it paused
    await page.getByTestId("ts-prev").click();
    await expect(page.getByTestId("ts-n")).toHaveText(`1/${hits.length}`);
    await page.keyboard.press("Shift+Enter");                                         // wraps to the last
    await expect(page.getByTestId("ts-n")).toHaveText(`${hits.length}/${hits.length}`);
    expect((await scan(page)).bad).toEqual([]);
    await page.screenshot({ path: `test-results/transcript-search-${theme}.png` });

    await page.getByTestId("ts-in").fill("没有这句话");
    await expect(page.getByTestId("ts-n")).toHaveText("无结果");
    await expect(page.locator(".ts-hit, .ts-cur")).toHaveCount(0);
    await page.getByTestId("ts-in").press("Escape");
    await expect(page.getByTestId("ts-in")).toHaveValue("");
    await expect(page.getByTestId("ts-n")).toHaveCount(0);
    await expect(page.getByTestId("ts-tick")).toHaveCount(0);
  });
}
