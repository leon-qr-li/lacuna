import { expect, test } from "@playwright/test";

// review player speed (backlog item 6) and the 5 s either side of an edit (item 11); AI first-cut server
test.use({ baseURL: "http://127.0.0.1:8798" });

const rateOf = (page: import("@playwright/test").Page) =>
  page.getByTestId("ab-audio").evaluate((a: HTMLAudioElement) => ({ rate: a.playbackRate, pitch: a.preservesPitch }));

test("review speed: buttons and S switch the speed, pitch kept, choice remembered", async ({ page }) => {
  await page.goto("/");
  await page.evaluate(() => localStorage.removeItem("lacuna.reviewRate"));
  await page.getByRole("link", { name: /审阅改动/ }).click();
  const speed = page.getByTestId("review-speed");
  await expect(speed).toHaveText("1×");

  // each tap steps to the next speed
  await speed.click();
  await expect(speed).toHaveText("1.25×");
  await speed.click();
  await expect(speed).toHaveText("1.5×");
  await expect(speed).toHaveAccessibleName("播放速度 1.5×");
  await expect.poll(() => rateOf(page)).toEqual({ rate: 1.5, pitch: true });

  // S cycles 1.5 → 2 → 1 → 1.25
  await page.locator("body").click({ position: { x: 5, y: 5 } });
  await page.keyboard.press("s");
  await expect(speed).toHaveText("2×");
  await page.keyboard.press("s");
  await expect(speed).toHaveText("1×");
  await page.keyboard.press("s");
  await expect(speed).toHaveText("1.25×");

  // playing an edit keeps the chosen speed (a new source must not reset it)
  await page.getByRole("button", { name: /B · 剪后/ }).click();
  await expect.poll(() => page.getByTestId("ab-audio").evaluate((a: HTMLAudioElement) => a.currentTime > 0 || !a.paused)).toBe(true);
  await expect.poll(() => rateOf(page)).toEqual({ rate: 1.25, pitch: true });

  // next edit, and after a reload: still 1.25×
  await page.keyboard.press("ArrowRight");
  await expect(speed).toHaveText("1.25×");
  await page.reload();
  await expect(page.getByTestId("review-speed")).toHaveText("1.25×");

  // the shortcut card lists S
  await page.keyboard.press("?");
  await expect(page.getByTestId("review-shortcuts")).toContainText("切换播放速度");
  await page.evaluate(() => localStorage.removeItem("lacuna.reviewRate"));
});

test("A/B preview of an edit plays about 5 s either side", async ({ page, request }) => {
  const eps = await (await request.get("/api/episodes")).json();
  const id = (eps.episodes ?? eps)[0].id;
  const ep = await (await request.get(`/api/episodes/${id}`)).json();
  const edit = ep.edits.find((e: { t: number; len: number }) => e.t > 8 && e.t + e.len < ep.duration - 8);
  const ab = await (await request.get(`/api/episodes/${id}/edits/${edit.id}/ab`)).json();
  for (const side of [ab.before, ab.after]) {
    expect(side.edit_at).toBeCloseTo(5, 1);
    expect(side.duration - side.edit_at - side.edit_len).toBeCloseTo(5, 1);
  }
  await page.goto("/");
  await page.getByRole("link", { name: /审阅改动/ }).click();
  await expect(page.locator(".ab-seg")).toHaveAttribute("title", "前后各约 5 秒，切换时位置同步");
});
