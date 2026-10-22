import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// 配乐 design B: library on the left (▶, 放到 ▾, search), the open card's volume curve (dots to drag
// or move with the arrow keys), sliders with numbers and − / +, 更多设置 with ±5 s, the 用在 scope.
const INBOX = join(dirname(fileURLToPath(import.meta.url)), ".fixtures", "music_inbox");
const EP = encodeURIComponent("EP_TEST_合成");
type P = { id: string; role: string; bg_db: number | null; gain_db: number; solo_s: number | null; ramp_s: number | null; at_s?: number | null };

async function ensureAsset(request: APIRequestContext, file: string, kind: string) {
  const r = await request.post(`/api/library/upload?${new URLSearchParams({ name: file, kind, note: "" })}`, {
    headers: { "Content-Type": "application/octet-stream" },
    data: readFileSync(join(INBOX, file)),
  });
  expect(r.ok()).toBeTruthy();
  const j = await r.json();
  return { id: j.asset.id as string, added: !j.duplicate };
}
const placements = async (page: Page) => ((await (await page.request.get(`/api/episodes/${EP}/music`)).json()).placements as P[]);

const added: string[] = [];
test.afterEach(async ({ request }) => {
  const m = await (await request.get(`/api/episodes/${EP}/music`)).json();
  for (const p of m.placements as P[]) await request.delete(`/api/episodes/${EP}/music/${p.id}`);
  for (const id of added.splice(0)) await request.delete(`/api/library/assets/${id}`);
});

test("library ▶ and 放到 ▾, the curve's dots, sliders with − / +, 更多设置 ±5 s, 用在", async ({ page }) => {
  for (const [f, k] of [["洛城片头.wav", "intro"], ["odyssey_theme.mp3", "other"]]) {
    const a = await ensureAsset(page.request, f, k);
    if (a.added) added.push(a.id);
  }
  for (const p of await placements(page)) await page.request.delete(`/api/episodes/${EP}/music/${p.id}`);
  await page.goto(`/#/ep/${EP}/music`);
  const lib = page.getByTestId("music-library");
  await expect(lib.getByTestId("music-asset")).toHaveCount(2);
  await expect(lib).toContainText("请只上传你有权使用的音乐");

  // ▶ hears the file itself
  const jingle = lib.getByTestId("music-asset").filter({ hasText: "洛城片头" });
  await jingle.getByRole("button", { name: /^试听/ }).click();
  await expect.poll(() => page.getByTestId("asset-audio").evaluate((a: HTMLAudioElement) => a.currentTime)).toBeGreaterThan(0.1);
  await jingle.getByRole("button", { name: /^停止试听/ }).click();

  // 放到 ▾ → 片头: the card opens with its curve
  await jingle.getByRole("button", { name: "放到 ▾" }).click();
  await page.getByRole("menuitem", { name: "片头" }).click();
  const intro = page.locator('[data-testid="placement"][data-role="intro"]');
  await expect(intro).toHaveCount(1);
  await expect(intro.getByTestId("placement-toggle")).toHaveAttribute("aria-expanded", "true");
  await expect(intro.getByTestId("music-curve")).toBeVisible();
  await expect(intro.getByTestId("curve-dot-low")).toContainText("说话时压低 22 dB");

  // the 说话时压低 dot: down arrow = 1 dB lower under the talk; dragging it down lowers it more
  await intro.getByTestId("curve-dot-low").focus();
  await page.keyboard.press("ArrowDown");
  await expect.poll(async () => (await placements(page))[0].bg_db).toBe(23);
  const dot = (await intro.getByTestId("curve-dot-low").boundingBox())!;
  await page.mouse.move(dot.x + dot.width / 2, dot.y + dot.height / 2);
  await page.mouse.down();
  await page.mouse.move(dot.x + dot.width / 2, dot.y + dot.height / 2 + 25, { steps: 4 });
  await page.mouse.up();
  await expect.poll(async () => (await placements(page))[0].bg_db!).toBeGreaterThanOrEqual(25);

  // sliders: − / + one step, the number typed in + Enter
  await intro.getByRole("button", { name: "音乐音量 少一点" }).click();
  await expect.poll(async () => (await placements(page))[0].gain_db).toBe(-0.5);
  await expect(intro.getByLabel("音量（dB）")).toHaveValue("-0.5");
  await intro.getByLabel("只放音乐（秒）").fill("4");
  await intro.getByLabel("只放音乐（秒）").press("Enter");
  await expect.poll(async () => (await placements(page))[0].solo_s).toBe(4);
  await expect(intro.getByTestId("curve-dot-solo")).toContainText("只放音乐 4 秒");

  // an interlude where the player is, then ±5 s under 更多设置
  const theme = lib.getByTestId("music-asset").filter({ hasText: /Odyssey|odyssey/ });
  await page.getByRole("button", { name: "前进 5 秒" }).click();
  await page.getByRole("button", { name: "前进 5 秒" }).click();
  await theme.getByRole("button", { name: "放到 ▾" }).click();
  await page.getByRole("menuitem", { name: /间奏 \/ 休息间隙（放在 0:\d\d）/ }).click();
  const mid = page.locator('[data-testid="placement"][data-role="interlude"]');
  await expect(mid.getByTestId("placement-toggle")).toHaveAttribute("aria-expanded", "true");
  await expect(intro.getByTestId("placement-toggle")).toHaveAttribute("aria-expanded", "false"); // one open card
  await mid.getByTestId("music-more").click();
  const at = async () => (await placements(page)).find((p) => p.role === "interlude")!.at_s!;
  const was = await at();
  await mid.getByRole("button", { name: "+5 秒" }).click();
  await expect.poll(at).toBeCloseTo(was + 5, 0);
  await mid.getByRole("button", { name: "−5 秒" }).click();
  await expect.poll(at).toBeCloseTo(was, 0);

  // 用在: only this episode doesn't change later episodes
  const scope = page.getByTestId("save-scope");
  await scope.getByRole("radio", { name: "只这一集" }).click();
  await expect(page.getByTestId("save-defaults")).toBeDisabled();
  await scope.getByRole("radio", { name: "整个节目" }).click();
  await expect(page.getByTestId("save-defaults")).toBeEnabled();

  for (const mode of ["dark", "light"]) {
    await page.evaluate((t) => localStorage.setItem("lacuna.theme", t), mode);
    await page.reload();
    await expect(page.getByTestId("music-curve")).toBeVisible();
    await page.screenshot({ path: `test-results/music-b-${mode}.png`, fullPage: true });
  }
});
