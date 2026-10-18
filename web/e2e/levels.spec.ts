import { expect, test, type Page } from "@playwright/test";

// 声音 (backlog 7): both hosts evened out, per-track gain, volume from the chat, clipped spots.
// The synthetic episode's first cut already raises Leon by 3 dB (its "响度匹配" edit). Every test
// leaves the episode's gains as it found them (the backend is shared with the other specs).

const EP = encodeURIComponent("EP_TEST_合成");
const SHOTS = process.env.LACUNA_SHOTS; // optional folder for screenshots (visual check, light + dark)

async function openLevels(page: Page) {
  await page.goto(`/#/ep/${EP}/levels`);
  await expect(page.getByTestId("levels")).toBeVisible();
}

const gain = (page: Page, name: string) => page.getByTestId(`levels-gain-${name}`);
const gains = (page: Page) =>
  page.evaluate(async (ep) => {
    const r = await fetch(`/api/episodes/${ep}/levels`).then((x) => x.json());
    return Object.fromEntries(r.tracks.map((t: { name: string; gain_db: number }) => [t.name, t.gain_db]));
  }, EP);

test.describe.serial("声音", () => {
  test("the step sits after 整集试听 and shows both hosts", async ({ page }) => {
    await page.goto(`/#/ep/${EP}/listen`);
    const steps = page.getByRole("navigation", { name: "制作流程" }).getByRole("link");
    await expect(steps.filter({ hasText: "声音" })).toBeVisible();
    const names = (await steps.allInnerTexts()).map((x) => x.trim());
    expect(names.indexOf("声音")).toBe(names.indexOf("整集试听") + 1);
    await steps.filter({ hasText: "声音" }).click();
    await expect(page).toHaveURL(/\/levels$/);
    await expect(page.getByTestId("levels-track-Leon")).toContainText("LUFS");
    await expect(gain(page, "Leon")).toHaveText("+3.0 dB");
    await expect(gain(page, "Pei")).toHaveText("±0.0 dB");
    await expect(page.getByTestId("levels")).toContainText("相差约");
  });

  test("统一两人音量 evens them out in one undoable step", async ({ page }) => {
    await openLevels(page);
    const before = await gains(page);
    await page.getByTestId("levels-auto").click();
    await expect(page.locator(".toast")).toContainText("两人音量已统一");
    await expect(page.getByTestId("levels")).toContainText("两人已经一样响");
    for (const n of ["Leon", "Pei"]) await expect(page.getByTestId(`levels-track-${n}`)).toContainText("现在 -20.0 LUFS");
    await expect(page.getByTestId("levels-auto")).toHaveText("重新统一");
    // the header's undo knows it and takes both gains back
    await page.getByRole("button", { name: "撤销" }).click();
    await expect(page.locator(".toast")).toContainText("统一两人音量");
    await expect(gain(page, "Leon")).toHaveText("+3.0 dB");
    expect(await gains(page)).toEqual(before);
  });

  test("−1 / +1 and the slider change one track; the player streams the new version", async ({ page }) => {
    await openLevels(page);
    await expect(page.getByTestId("levels-audio")).toHaveAttribute("src", /\/audio\/.+\.wav$/);
    const src0 = await page.getByTestId("levels-audio").getAttribute("src");
    await page.getByRole("button", { name: "Pei 大 1 dB" }).click();
    await expect.poll(() => gains(page)).toEqual({ Leon: 3, Pei: 1 });
    await expect(page.getByTestId("levels-audio")).not.toHaveAttribute("src", src0 ?? "");
    await page.getByRole("slider", { name: "Pei 的增益" }).fill("-4.5");
    await expect(gain(page, "Pei")).toHaveText("−4.5 dB");
    await expect.poll(() => gains(page)).toEqual({ Leon: 3, Pei: -4.5 });
    await expect(page.getByRole("button", { name: /用建议值/ }).first()).toBeVisible();
    // back to where it was: two undo steps
    await page.getByRole("button", { name: "撤销" }).click();
    await expect(page.locator(".toast")).toContainText("已撤销");
    await page.getByRole("button", { name: "撤销" }).click();
    await expect.poll(() => gains(page)).toEqual({ Leon: 3, Pei: 0 });
    await expect(gain(page, "Pei")).toHaveText("±0.0 dB");
  });

  test("「Pei 的声音太小了」 in the chat raises her without asking the AI", async ({ page }) => {
    await page.goto(`/#/ep/${EP}/listen`);
    await page.getByLabel(/对 AI 制作人说/).fill("Pei 的声音太小了");
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("chat-log")).toContainText("Pei 的音量调高了 2 dB（现在 Pei +2.0 dB）");
    await expect(page.getByTestId("proposal")).toHaveCount(0); // applied at once, nothing to approve
    await page.getByRole("link", { name: "声音", exact: true }).click();
    await expect(gain(page, "Pei")).toHaveText("+2.0 dB");
    await page.getByRole("button", { name: "撤销" }).click();
    await expect(gain(page, "Pei")).toHaveText("±0.0 dB");
  });

  test("clipped spots are listed and play from 2 s before", async ({ page }) => {
    // the synthetic recordings never clip: add three spots to Pei's measurement
    await page.route(/\/levels$/, async (route) => {
      if (route.request().method() !== "GET") return route.fallback();
      const r = await route.fetch();
      const body = await r.json();
      body.tracks[1] = { ...body.tracks[1], clip_count: 3, clip_times: [12.4, 33.0, 47.25] };
      await route.fulfill({ response: r, json: body });
    });
    await openLevels(page);
    const box = page.getByTestId("levels-clips");
    await expect(box).toContainText("Pei：3 处");
    await box.getByRole("button", { name: "0:33" }).click();
    const audio = page.getByTestId("levels-audio");
    await expect.poll(() => audio.evaluate((a: HTMLAudioElement) => !a.paused && a.currentTime >= 30.9)).toBe(true);
    await page.getByTestId("levels").getByTestId("play").click(); // pause
  });

  for (const theme of ["light", "dark"] as const) {
    test(`reads well in ${theme} mode, in English too`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: theme });
      await page.goto("/");
      await page.evaluate((t) => localStorage.setItem("lacuna.theme", t), theme);
      await openLevels(page);
      await expect(page.getByTestId("levels-track-Pei")).toContainText("LUFS");
      // the controls fit on one row next to the name
      const ctl = await page.getByTestId("levels-track-Leon").locator(".levels-ctl").boundingBox();
      const name = await page.getByTestId("levels-track-Leon").locator(".levels-name").boundingBox();
      expect(ctl && name && Math.abs(ctl.y + ctl.height / 2 - (name.y + name.height / 2)) < 20).toBe(true);
      if (SHOTS) await page.screenshot({ path: `${SHOTS}/levels_${theme}.png`, fullPage: true });
      await page.evaluate(() => localStorage.setItem("lacuna.lang", "en"));
      await page.reload();
      await expect(page.getByTestId("levels")).toContainText("The hosts' volume");
      await expect(page.getByRole("link", { name: "Volume", exact: true })).toBeVisible();
      if (SHOTS) await page.screenshot({ path: `${SHOTS}/levels_${theme}_en.png`, fullPage: true });
      // back to Chinese, so the server's language (kept from the last request) is Chinese again
      await page.evaluate(() => localStorage.setItem("lacuna.lang", "zh"));
      await page.reload();
      await expect(page.getByTestId("levels")).toContainText("两人的音量");
    });
  }
});

// item 20: each music placement says how much it was levelled automatically (AI-cut backend, its own library)
test.describe("music level", () => {
  test.use({ baseURL: "http://127.0.0.1:8798" });

  test("a placement shows its automatic level next to 音量（dB）", async ({ page, request }) => {
    const { readFileSync } = await import("node:fs");
    const { dirname, join } = await import("node:path");
    const { fileURLToPath } = await import("node:url");
    const song = join(dirname(fileURLToPath(import.meta.url)), ".fixtures", "music_inbox", "odyssey_theme.mp3");
    const up = await request.post("/api/library/upload?name=level_test.mp3&kind=bed", {
      headers: { "content-type": "application/octet-stream" },
      data: readFileSync(song),
    });
    expect(up.ok()).toBe(true);
    const asset = (await up.json()).asset.id;
    const ep = encodeURIComponent("EP_AI_合成");
    const add = await request.post(`/api/episodes/${ep}/music`, { data: { asset_id: asset, role: "bed", at_s: 5 } });
    expect(add.ok()).toBe(true);
    try {
      await page.goto(`/#/ep/${ep}/music`);
      const row = page.getByTestId("placement").filter({ hasText: "level_test.mp3" });
      await expect(row.getByTestId("placement-level")).toContainText(/已自动调平 [+−±]\d+\.\d dB/);
    } finally {
      const m = await (await request.get(`/api/episodes/${ep}/music`)).json();
      for (const p of m.placements) if (p.asset_id === asset) await request.delete(`/api/episodes/${ep}/music/${p.id}`);
      await request.delete(`/api/library/assets/${asset}`);
    }
  });
});
