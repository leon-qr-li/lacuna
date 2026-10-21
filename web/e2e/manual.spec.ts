import { expect, test, type Page } from "@playwright/test";
import { SCOPES_PORT } from "../playwright.config";
import { undoKey } from "./undo";

// 手动剪辑 (decision manual-editing): select a stretch on the waveform or the transcript, cut it from every
// track or silence one host; it is an ordinary undoable edit. Runs on the scopes server (its own state).
test.use({ baseURL: `http://127.0.0.1:${SCOPES_PORT}` });
const EP = "EP_TEST_合成";

async function open(page: Page) {
  await page.goto(`/#/ep/${encodeURIComponent(EP)}/listen`);
  await expect(page.getByTestId("edit-lanes")).toBeVisible();
  await expect(page.getByTestId("lane-Leon").locator("canvas")).toBeVisible();
}

async function dragLane(page: Page, lane: string, from: number, to: number) {
  const box = (await page.getByTestId(`lane-${lane}`).boundingBox())!;
  await page.mouse.move(box.x + box.width * from, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * to, box.y + box.height / 2, { steps: 8 });
  await page.mouse.up();
}

const duration = async (page: Page) =>
  (await (await page.request.get(`/api/episodes/${encodeURIComponent(EP)}`)).json()).duration as number;

test.describe.serial("manual editing", () => {
  test("drag selects on every lane; Esc drops it; a click only seeks", async ({ page }) => {
    await open(page);
    await dragLane(page, "Leon", 0.3, 0.4);
    await expect(page.getByTestId("ml-bar")).toContainText("已选");
    await expect(page.getByTestId("ml-sel")).toHaveCount(2); // the selection shows on both lanes
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("ml-bar")).toBeHidden();
    await page.getByTestId("lane-Pei").click({ position: { x: 200, y: 20 } });
    await expect(page.getByTestId("ml-bar")).toBeHidden();
    await expect(page.getByTestId("clock")).not.toContainText("0:00 /");
  });

  const view = async (page: Page) => {
    const el = page.getByTestId("edit-lanes");
    return { start: Number(await el.getAttribute("data-start")), span: Number(await el.getAttribute("data-span")) };
  };

  test("Ctrl + wheel zooms the timeline smoothly around the pointer, not the page; 暂停时回退 5 秒 starts unticked", async ({ page }) => {
    await page.addInitScript(() => localStorage.removeItem("lacuna.rewindOnPause"));
    await open(page);
    await expect(page.getByLabel("暂停时回退 5 秒")).not.toBeChecked();
    await expect(page.getByTestId("edit-lanes").getByRole("button", { name: /^\d+\s*秒$/ })).toHaveCount(0); // no zoom buttons
    const before = await view(page);
    const lane = (await page.getByTestId("lane-Leon").boundingBox())!;
    await page.mouse.move(lane.x + lane.width / 2, lane.y + lane.height / 2);
    await page.keyboard.down("Control");
    await page.mouse.wheel(0, -100);
    await page.keyboard.up("Control");
    await expect.poll(async () => (await view(page)).span).toBeLessThan(before.span);
    const z1 = (await view(page)).span;
    expect(z1).toBeGreaterThan(before.span * 0.6); // one notch is a small step, not a jump to the next preset
    // the page itself never zooms: the event is cancelled
    const cancelled = await page.getByTestId("lane-Pei").evaluate((el) => {
      const ev = new WheelEvent("wheel", { deltaY: 100, ctrlKey: true, bubbles: true, cancelable: true });
      el.dispatchEvent(ev);
      return ev.defaultPrevented;
    });
    expect(cancelled).toBe(true);
    const outside = await page.locator("body").evaluate((el) => {
      const ev = new WheelEvent("wheel", { deltaY: 100, bubbles: true, cancelable: true });
      el.dispatchEvent(ev);
      return ev.defaultPrevented;
    });
    expect(outside).toBe(false); // the wheel elsewhere still scrolls the page
  });

  test("a click on a lane moves the playhead but not the timeline; dragging the ruler pans it", async ({ page }) => {
    await open(page);
    const lane = (await page.getByTestId("lane-Leon").boundingBox())!;
    await page.mouse.move(lane.x + lane.width / 2, lane.y + lane.height / 2);
    await page.keyboard.down("Control");
    for (let i = 0; i < 6; i++) await page.mouse.wheel(0, -100);
    await page.keyboard.up("Control");
    const v0 = await view(page);
    await page.getByTestId("lane-Pei").click({ position: { x: lane.width * 0.9, y: 20 } });
    await expect(page.getByTestId("clock")).not.toContainText("0:00 /");
    await page.waitForTimeout(300);
    expect(await view(page)).toEqual(v0); // not re-centred on the click
    const ruler = (await page.getByTestId("ml-ruler").boundingBox())!;
    await page.mouse.move(ruler.x + ruler.width * 0.6, ruler.y + ruler.height / 2);
    await page.mouse.down();
    await page.mouse.move(ruler.x + ruler.width * 0.3, ruler.y + ruler.height / 2, { steps: 6 });
    await page.mouse.up();
    await expect.poll(async () => (await view(page)).start).toBeGreaterThan(v0.start);
    await expect(page.getByTestId("ml-bar")).toHaveCount(0); // panning never selects
  });

  test("holding Space turns the lanes into a hand that pans; a Space tap still plays", async ({ page }) => {
    await open(page);
    await page.getByLabel("暂停时回退 5 秒").uncheck();
    const lane = (await page.getByTestId("lane-Leon").boundingBox())!;
    await page.mouse.move(lane.x + lane.width / 2, lane.y + lane.height / 2);
    await page.keyboard.down("Control");
    for (let i = 0; i < 6; i++) await page.mouse.wheel(0, -100);
    await page.keyboard.up("Control");
    const v0 = await view(page);
    await page.mouse.move(lane.x + lane.width * 0.3, lane.y + lane.height / 2);
    await page.keyboard.down(" ");
    await expect(page.getByTestId("edit-lanes")).toHaveClass(/is-hand/);
    await page.mouse.down();
    await page.mouse.move(lane.x + lane.width * 0.7, lane.y + lane.height / 2, { steps: 6 });
    await page.mouse.up();
    await page.keyboard.up(" ");
    await expect(page.getByTestId("edit-lanes")).not.toHaveClass(/is-hand/);
    expect((await view(page)).start).toBeLessThan(v0.start); // dragged right: earlier audio comes into view
    await expect(page.getByTestId("ml-bar")).toHaveCount(0);
    await expect(page.getByTestId("play")).toHaveAttribute("aria-label", "播放"); // a pan is not a play
    await page.keyboard.press(" ");
    await expect(page.getByTestId("play")).toHaveAttribute("aria-label", "暂停");
    await page.keyboard.press(" ");
    await expect(page.getByTestId("play")).toHaveAttribute("aria-label", "播放");
  });

  test("playing past the right edge turns the timeline a page", async ({ page }) => {
    await open(page);
    await page.getByLabel("暂停时回退 5 秒").uncheck();
    const lane = (await page.getByTestId("lane-Leon").boundingBox())!;
    await page.mouse.move(lane.x + lane.width / 2, lane.y + lane.height / 2);
    await page.keyboard.down("Control");
    for (let i = 0; i < 12; i++) await page.mouse.wheel(0, -100);
    await page.keyboard.up("Control");
    await page.getByTestId("lane-Leon").click({ position: { x: lane.width * 0.92, y: 20 } });
    const v0 = await view(page);
    await page.getByTestId("play").click();
    await expect.poll(async () => (await view(page)).start, { timeout: 15_000 }).toBeGreaterThan(v0.start + v0.span * 0.5);
    await page.getByTestId("play").click();
  });

  test("with a selection, play plays just the selection and comes back to its start", async ({ page }) => {
    await open(page);
    await page.getByLabel("暂停时回退 5 秒").uncheck();
    await dragLane(page, "Leon", 0.3, 0.36);
    await expect(page.getByTestId("ml-bar")).toBeVisible();
    const text = (await page.getByTestId("ml-bar").locator(".ml-what b").textContent()) ?? "";
    const [a, b] = text.split("–").map((x) => {
      const [m, s] = x.trim().split(":");
      return Number(m) * 60 + Number(s);
    });
    const audio = page.getByTestId("main-audio");
    await page.getByTestId("play").click();
    await expect(page.getByTestId("play")).toHaveAttribute("aria-label", "暂停");
    await expect(page.getByTestId("play")).toHaveAttribute("aria-label", "播放", { timeout: 15_000 }); // stops by itself
    const at = await audio.evaluate((el: HTMLAudioElement) => el.currentTime);
    expect(at).toBeCloseTo(a, 0); // back at the start of the selection
    expect(b).toBeGreaterThan(a);
    await expect(page.getByTestId("ml-bar")).toBeVisible(); // the selection stays
  });

  test("on a selection edge the pointer turns into a resize cursor, and dragging it resizes", async ({ page }) => {
    await open(page);
    await dragLane(page, "Leon", 0.3, 0.4);
    const lane = page.getByTestId("lane-Leon");
    const box = (await lane.boundingBox())!;
    await page.mouse.move(box.x + box.width * 0.2, box.y + box.height / 2);
    await expect(lane).not.toHaveClass(/is-edge/);
    await page.mouse.move(box.x + box.width * 0.4, box.y + box.height / 2);
    await expect(lane).toHaveClass(/is-edge/);
    expect(await lane.evaluate((el) => getComputedStyle(el).cursor)).toBe("col-resize");
    const before = await page.getByTestId("ml-bar").locator(".ml-what b").textContent();
    await page.mouse.down();
    await page.mouse.move(box.x + box.width * 0.5, box.y + box.height / 2, { steps: 5 });
    await page.mouse.up();
    await expect(page.getByTestId("ml-bar").locator(".ml-what b")).not.toHaveText(before ?? "");
    await expect(lane).not.toHaveClass(/is-edge/);
  });

  test("the ? next to the title explains the timeline on hover", async ({ page }) => {
    await open(page);
    const tip = page.locator("#ml-help-tip");
    await expect(tip).toBeHidden();
    await page.getByTestId("ml-help").hover();
    await expect(tip).toBeVisible();
    await expect(tip).toContainText("按住空格拖");
    await expect(tip).toContainText("Ctrl + X");
  });

  test("cut from both tracks, shows as 手动剪辑, undo brings it back", async ({ page }) => {
    await open(page);
    const before = await duration(page);
    await dragLane(page, "Leon", 0.55, 0.62);
    await page.getByTestId("ml-cut").click();
    await expect(page.locator(".toast")).toContainText("已删掉");
    await expect(page.getByTestId("ml-bar")).toBeHidden();
    await page.getByTestId("tab-near").click();
    const row = page.locator('[data-testid="nearby"] li[data-source="manual"]');
    await expect(row).toHaveCount(1);
    await expect(row).toContainText("手动删除");
    await expect(row).toContainText("手动剪辑");
    expect(await duration(page)).toBeLessThan(before - 1);
    await undoKey(page);
    await expect(page.locator(".toast")).toContainText("已撤销：手动剪辑：");
    await expect(row).toHaveCount(0);
    expect(await duration(page)).toBeCloseTo(before, 2);
  });

  test("silence one host: marked on that lane only, timeline unchanged", async ({ page }) => {
    await open(page);
    const before = await duration(page);
    await dragLane(page, "Pei", 0.2, 0.3);
    await page.getByTestId("ml-mute-Pei").click();
    await expect(page.locator(".toast")).toContainText("已静音 Pei");
    await expect(page.getByTestId("lane-Pei").locator('.mark-span[data-title^="Pei 单轨静音"]')).toHaveCount(1);
    await expect(page.getByTestId("lane-Leon").locator('.mark-span[data-title^="Pei 单轨静音"]')).toHaveCount(0);
    expect(await duration(page)).toBeCloseTo(before, 2);
    // Ctrl + X on a new selection cuts it from every track
    await dragLane(page, "Leon", 0.7, 0.75);
    await page.keyboard.press("Control+x");
    await expect(page.locator(".toast")).toContainText("已删掉");
    await undoKey(page);
    await undoKey(page);
    await page.getByTestId("tab-near").click();
    await expect(page.locator(".side-near")).toBeVisible();
    await expect(page.locator('[data-testid="nearby"] li[data-source="manual"]')).toHaveCount(0);
  });

  test("select by dragging across transcript words, cut, then restore the struck words", async ({ page }) => {
    await open(page);
    const words = page.getByTestId("ml-tx").locator(".ml-w");
    await expect(words.nth(5)).toBeVisible();
    const a = (await words.nth(1).boundingBox())!;
    const b = (await words.nth(4).boundingBox())!;
    await page.mouse.move(a.x + 3, a.y + a.height / 2);
    await page.mouse.down();
    await page.mouse.move(b.x + 3, b.y + b.height / 2, { steps: 6 });
    await page.mouse.up();
    const bar = page.getByTestId("transcript-edit").getByTestId("ml-bar");
    await expect(bar).toContainText("已选 Leon");
    await expect(page.getByTestId("ml-tx").locator(".ml-w.is-sel")).toHaveCount(4);
    await expect(page.getByTestId("ml-sel")).toHaveCount(2); // the same stretch on the timeline
    await expect(bar.getByTestId("ml-mute-Pei")).toHaveCount(0); // only the host whose words are selected
    await bar.getByTestId("ml-cut").click();
    await expect(page.locator(".toast")).toContainText("已删掉");
    // wait for the manual cut itself: the AI's cuts are struck already, before the transcript reloads
    await expect(page.getByTestId("ml-tx").locator("s.ml-gone[data-edit^='m']")).not.toHaveCount(0);
    const manualId = await page.getByTestId("ml-tx").locator("s.ml-gone").evaluateAll(
      (els) => els.map((e) => e.getAttribute("data-edit")).find((x) => x?.startsWith("m")) ?? "",
    );
    expect(manualId).not.toBe("");
    await page.getByTestId("ml-tx").locator(`s.ml-gone[data-edit="${manualId}"]`).click();
    await expect(page.locator(".toast")).toContainText("已恢复原话");
    await expect(page.getByTestId("ml-tx").locator(`s.ml-gone[data-edit="${manualId}"]`)).toHaveCount(0);
  });

  test("a click on one word selects just that word and jumps there; a second click drops it", async ({ page }) => {
    await open(page);
    const w = page.getByTestId("ml-tx").locator(".ml-w").nth(20);
    await w.click();
    const sel = page.getByTestId("ml-tx").locator(".ml-w.is-sel");
    await expect(sel).toHaveCount(1);
    await expect(w).toHaveClass(/is-sel/);
    // read the word once it is selected: the transcript can re-render while the page settles (Windows CI)
    const text = ((await sel.textContent()) ?? "").trim();
    await expect(page.getByTestId("ml-bar")).toContainText(`「${text}」`);
    await expect(page.getByTestId("clock")).not.toContainText("0:00 /");
    await w.click();
    await expect(page.getByTestId("ml-bar")).toHaveCount(0);
  });

  test("a single selected word can be cut", async ({ page }) => {
    await open(page);
    const w = page.getByTestId("ml-tx").locator(".ml-w").nth(8);
    await w.click();
    await page.getByTestId("transcript-edit").getByTestId("ml-cut").click();
    await expect(page.locator(".toast")).toContainText("已删掉");
    await expect(page.getByTestId("ml-tx").locator("s.ml-gone[data-edit^='m']")).not.toHaveCount(0);
  });
});
