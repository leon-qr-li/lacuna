import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test, type APIRequestContext, type Locator, type Page } from "@playwright/test";

// 首次检测 15-22 on the music page: file names first in the picker, 22 dB default, the full-volume
// label, ±5 s, the strip and the player always together, automatic / looping beds, changing a use.
const INBOX = join(dirname(fileURLToPath(import.meta.url)), ".fixtures", "music_inbox");
const EP = encodeURIComponent("EP_TEST_合成");

type Asset = { id: string; name: string };
type P = { id: string; role: string; start_s: number | null; end_s: number | null; listen_s?: number; auto?: boolean; loop?: boolean; gain_db: number };

async function ensureAsset(request: APIRequestContext, file: string, kind: string): Promise<{ asset: Asset; added: boolean }> {
  const r = await request.post(`/api/library/upload?${new URLSearchParams({ name: file, kind, note: "" })}`, {
    headers: { "Content-Type": "application/octet-stream" },
    data: readFileSync(join(INBOX, file)),
  });
  expect(r.ok()).toBeTruthy();
  const j = await r.json();
  return { asset: j.asset, added: !j.duplicate };
}

const music = async (page: Page) => (await (await page.request.get(`/api/episodes/${EP}/music`)).json()) as { placements: P[]; duration: number };
const secs = (s: string) => s.split(":").reduce((a, x) => a * 60 + Number(x), 0);
const mixTime = (page: Page) => page.getByTestId("mix-audio").evaluate((a: HTMLAudioElement) => a.currentTime);

// 配乐 design B: one card is open at a time; 更多设置 holds the less used numbers
async function openCard(card: Locator) {
  const b = card.getByTestId("placement-toggle");
  if ((await b.getAttribute("aria-expanded")) !== "true") await b.click();
  await expect(b).toHaveAttribute("aria-expanded", "true");
}
async function more(card: Locator) {
  await openCard(card);
  const b = card.getByTestId("music-more");
  if ((await b.getAttribute("aria-expanded")) !== "true") await b.click();
}

const added: string[] = [];
// leave the shared episode and library as they were, also when a check fails
test.afterEach(async ({ request }) => {
  const m = await (await request.get(`/api/episodes/${EP}/music`)).json();
  for (const p of m.placements as P[]) await request.delete(`/api/episodes/${EP}/music/${p.id}`);
  for (const id of added.splice(0)) await request.delete(`/api/library/assets/${id}`);
});

test("music page: picker, defaults, player and strip together, beds, changing a use", async ({ page }) => {
  const theme = await ensureAsset(page.request, "odyssey_theme.mp3", "other");
  const jingle = await ensureAsset(page.request, "洛城片头.wav", "intro");
  for (const a of [theme, jingle]) if (a.added) added.push(a.asset.id);
  for (const p of (await music(page)).placements) await page.request.delete(`/api/episodes/${EP}/music/${p.id}`);

  await page.goto(`/#/ep/${EP}/music`);
  await expect(page.getByRole("heading", { name: "配乐", exact: true })).toBeVisible();

  // 15: every choice starts with the file name
  const options = await page.getByLabel("选择素材").locator("option").allInnerTexts();
  expect(options.length).toBeGreaterThanOrEqual(2);
  const lib = (await (await page.request.get("/api/library")).json()).assets as Asset[];
  for (const o of options) expect(lib.some((a) => o.startsWith(`${a.name} - `) || o.startsWith(`${a.name} · `))).toBeTruthy();
  expect(options.some((o) => o.startsWith("洛城片头.wav"))).toBeTruthy();

  // the intro, then an interlude at 0:20
  await page.getByLabel("选择素材").selectOption(jingle.asset.id);
  await page.getByRole("button", { name: "放进去" }).click();
  const intro = page.getByTestId("placement").filter({ hasText: "洛城片头.wav" });
  await expect(intro).toHaveCount(1);
  // 16: background 22 dB lower by default
  await expect(intro.getByLabel("背景压低（dB）")).toHaveValue("22");
  await page.getByLabel("选择素材").selectOption(theme.asset.id);
  await page.getByLabel("用途").selectOption("interlude");
  await page.getByLabel("位置", { exact: true }).fill("0:20");
  await page.getByRole("button", { name: "放进去" }).click();
  await expect(page.getByTestId("placement")).toHaveCount(2);
  const mid = page.getByTestId("placement").filter({ hasText: "odyssey_theme.mp3" });
  // 17: the gap's full-volume time says what it is
  await expect(mid.getByLabel("全音量时长（秒）")).toHaveValue("15");
  await expect(page.getByText("正常音量")).toHaveCount(0);
  await expect(mid.getByTestId("placement-plan")).toContainText("全音量 15 秒");

  // 18: ±5 s on the player
  const clock = page.getByTestId("mix-clock");
  await expect(clock).toContainText("0:00 /");
  await page.getByRole("button", { name: "前进 5 秒" }).click();
  await expect.poll(() => mixTime(page)).toBeCloseTo(5, 0);
  await expect(clock).toContainText("0:05 /");
  await page.getByRole("button", { name: "前进 5 秒" }).click();
  await page.getByRole("button", { name: "后退 5 秒" }).click();
  await expect.poll(() => mixTime(page)).toBeCloseTo(5, 0);

  // 验收 V8: speed chip on the mix player, pitch kept, remembered after a reload
  const speed = page.getByTestId("mix-speed");
  const rateOf = () => page.getByTestId("mix-audio").evaluate((a: HTMLAudioElement) => ({ rate: a.playbackRate, pitch: a.preservesPitch }));
  await expect(speed).toHaveText("1×");
  await speed.click();
  await speed.click();
  await expect(speed).toHaveText("1.5×");
  await expect(speed).toHaveAccessibleName("播放速度 1.5×");
  await expect.poll(rateOf).toEqual({ rate: 1.5, pitch: true });
  await page.reload();
  await expect(page.getByTestId("mix-speed")).toHaveText("1.5×");
  await expect.poll(rateOf).toEqual({ rate: 1.5, pitch: true });
  await page.getByTestId("mix-speed").click();
  await page.getByTestId("mix-speed").click(); // 2× → 1×
  await expect(page.getByTestId("mix-speed")).toHaveText("1×");
  await page.getByRole("button", { name: "前进 5 秒" }).click();
  await expect.poll(() => mixTime(page)).toBeCloseTo(5, 0);

  // 19: a block on the strip moves the player below (and plays), the playhead follows the player
  const m1 = await music(page);
  const gap = m1.placements.find((p) => p.role === "interlude")!;
  await page.getByTestId("mstrip-block").filter({ hasText: "间奏" }).click();
  await expect.poll(() => mixTime(page)).toBeGreaterThanOrEqual(gap.listen_s! - 0.01);
  await expect.poll(() => page.getByTestId("mix-audio").evaluate((a: HTMLAudioElement) => a.paused)).toBe(false);
  await expect(clock).toContainText(`${Math.floor(gap.listen_s! / 60)}:${String(Math.floor(gap.listen_s! % 60)).padStart(2, "0")}`);
  await expect(page.getByTestId("mstrip-block").filter({ hasText: "间奏" })).toHaveClass(/is-on/);
  await expect(mid.getByRole("button", { name: "停止" })).toBeVisible(); // the row knows it is playing
  const head = async () => parseFloat((await page.getByTestId("mstrip-head").getAttribute("style"))!.replace(/[^0-9.]/g, ""));
  const pct = (100 * (await mixTime(page))) / m1.duration;
  expect(Math.abs((await head()) - pct)).toBeLessThan(3);
  await mid.getByRole("button", { name: "停止" }).click();
  await expect.poll(() => page.getByTestId("mix-audio").evaluate((a: HTMLAudioElement) => a.paused)).toBe(true);
  // clicking the strip itself jumps there
  const box = (await page.getByTestId("mstrip").boundingBox())!;
  await page.getByTestId("mstrip").click({ position: { x: box.width * 0.75, y: 4 } });
  await expect.poll(() => mixTime(page)).toBeCloseTo(m1.duration * 0.75, -0.5);
  await page.getByTestId("mix-audio").evaluate((a: HTMLAudioElement) => a.pause());

  // 22: change the interlude into a bed and back, keeping its song and volume
  await openCard(mid); // after the reload the first card is the open one
  await mid.getByLabel("音量（dB）").fill("-4");
  await mid.getByRole("button", { name: "保存" }).click();
  await expect(page.getByTestId("music-msg")).toHaveText("已保存");
  await mid.getByLabel("改类型").selectOption("bed");
  await expect(page.getByTestId("music-msg")).toHaveText("已改成铺底");
  await more(mid);
  await expect(mid.getByTestId("bed-options")).toBeVisible();
  await expect(mid.getByLabel("音量（dB）")).toHaveValue("-4");
  await mid.getByLabel("改类型").selectOption("interlude");
  await expect(mid.getByLabel("全音量时长（秒）")).toHaveValue("15"); // the interlude's own default again
  await expect(mid.getByLabel("音量（dB）")).toHaveValue("-4");
  // the intro can't silently take another intro's place: the option says it replaces it
  await expect(mid.getByLabel("改类型").locator("option[value=intro]")).toHaveText("片头（替换现在的）");
  await mid.getByRole("button", { name: "去掉" }).click();
  await expect(page.getByTestId("placement")).toHaveCount(1);

  // 21: a bed with no position goes where no other music plays; it can loop to fill that stretch
  await page.getByLabel("选择素材").selectOption(theme.asset.id);
  await page.getByLabel("用途").selectOption("bed");
  await expect(page.getByLabel("位置", { exact: true })).toHaveAttribute("placeholder", "位置（空着 = 自动放进空档）");
  await page.getByLabel("循环填满").check();
  await page.getByRole("button", { name: "放进去" }).click();
  const bed = page.getByTestId("placement").filter({ hasText: "odyssey_theme.mp3" });
  await more(bed);
  await expect(bed.getByLabel("自动放进空档")).toBeChecked();
  await expect(bed.getByLabel("循环填满")).toBeChecked();
  await expect(bed.getByTestId("placement-plan")).toContainText("没有其他配乐的空档");
  await expect(bed.getByTestId("placement-plan")).toContainText("循环填满");
  let m2 = await music(page);
  const i2 = m2.placements.find((p) => p.role === "intro")!;
  let b2 = m2.placements.find((p) => p.role === "bed")!;
  expect(b2.auto && b2.loop).toBeTruthy();
  expect(b2.start_s).toBeCloseTo(i2.end_s!, 1); // right after the intro has played out
  expect(b2.end_s! - b2.start_s!).toBeGreaterThan(12); // longer than the 12 s song: it loops
  // a position written by hand wins; ticking the box hands it back to the App
  await bed.getByLabel("位置（成品时间）").fill("0:40");
  await bed.getByLabel("位置（成品时间）").press("Enter");
  await expect(bed.getByLabel("自动放进空档")).not.toBeChecked();
  await expect.poll(async () => secs(await bed.getByLabel("位置（成品时间）").inputValue())).toBe(40);
  await bed.getByLabel("自动放进空档").click(); // saved first, then shown ticked
  await expect(bed.getByLabel("自动放进空档")).toBeChecked();
  m2 = await music(page);
  b2 = m2.placements.find((p) => p.role === "bed")!;
  expect(b2.start_s).toBeCloseTo(i2.end_s!, 1);

  // both themes render the new controls
  for (const mode of ["dark", "light"]) {
    await page.evaluate((t) => localStorage.setItem("lacuna.theme", t), mode);
    await page.reload();
    await expect(page.getByTestId("mstrip-head")).toBeVisible();
    await page.screenshot({ path: `test-results/music-page-${mode}.png`, fullPage: true });
  }

});
