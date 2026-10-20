import { expect, test, type Page } from "@playwright/test";
import { SCOPES_PORT } from "../playwright.config";

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

  test("Ctrl + wheel over the timeline zooms it, not the page; 暂停时回退 5 秒 starts unticked", async ({ page }) => {
    await page.addInitScript(() => localStorage.removeItem("lacuna.rewindOnPause"));
    await open(page);
    await expect(page.getByLabel("暂停时回退 5 秒")).not.toBeChecked();
    const zoom = page.getByTestId("edit-lanes").getByRole("group", { name: "缩放" });
    await zoom.getByRole("button", { name: "30 秒" }).click();
    const lane = (await page.getByTestId("lane-Leon").boundingBox())!;
    await page.mouse.move(lane.x + lane.width / 2, lane.y + lane.height / 2);
    await page.keyboard.down("Control");
    await page.mouse.wheel(0, -100);
    await page.keyboard.up("Control");
    await expect(zoom.getByRole("button", { name: "10 秒" })).toHaveAttribute("aria-pressed", "true");
    await page.waitForTimeout(200);
    await page.keyboard.down("Control");
    await page.mouse.wheel(0, 100);
    await page.keyboard.up("Control");
    await expect(zoom.getByRole("button", { name: "30 秒" })).toHaveAttribute("aria-pressed", "true");
    // the page itself must not zoom: the event is cancelled
    const cancelled = await page.getByTestId("lane-Pei").evaluate((el) => {
      const ev = new WheelEvent("wheel", { deltaY: 100, ctrlKey: true, bubbles: true, cancelable: true });
      el.dispatchEvent(ev);
      return ev.defaultPrevented;
    });
    expect(cancelled).toBe(true);
    // a plain wheel still scrolls the page as before
    const plain = await page.getByTestId("lane-Pei").evaluate((el) => {
      const ev = new WheelEvent("wheel", { deltaY: 100, bubbles: true, cancelable: true });
      el.dispatchEvent(ev);
      return ev.defaultPrevented;
    });
    expect(plain).toBe(false);
  });

  test("cut from both tracks, shows as 手动剪辑, undo brings it back", async ({ page }) => {
    await open(page);
    const before = await duration(page);
    await page.getByRole("button", { name: "10 秒" }).click();
    await expect(page.getByRole("button", { name: "10 秒" })).toHaveAttribute("aria-pressed", "true");
    await page.getByRole("button", { name: "30 秒" }).click();
    await dragLane(page, "Leon", 0.55, 0.62);
    await page.getByTestId("ml-cut").click();
    await expect(page.locator(".toast")).toContainText("已删掉");
    await expect(page.getByTestId("ml-bar")).toBeHidden();
    const row = page.locator('[data-testid="nearby"] li[data-source="manual"]');
    await expect(row).toHaveCount(1);
    await expect(row).toContainText("手动删除");
    await expect(row).toContainText("手动剪辑");
    expect(await duration(page)).toBeLessThan(before - 1);
    await page.getByRole("button", { name: "撤销" }).click();
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
    await expect(page.getByTestId("lane-Pei").locator('.mark-span[title^="Pei 单轨静音"]')).toHaveCount(1);
    await expect(page.getByTestId("lane-Leon").locator('.mark-span[title^="Pei 单轨静音"]')).toHaveCount(0);
    expect(await duration(page)).toBeCloseTo(before, 2);
    // Del on a new selection cuts it from every track
    await dragLane(page, "Leon", 0.7, 0.75);
    await page.keyboard.press("Delete");
    await expect(page.locator(".toast")).toContainText("已删掉");
    await page.getByRole("button", { name: "撤销" }).click();
    await page.getByRole("button", { name: "撤销" }).click();
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
    await expect(page.getByTestId("ml-tx").locator("s.ml-gone")).not.toHaveCount(0);
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
    const text = (await w.textContent()) ?? "";
    await w.click();
    await expect(page.getByTestId("ml-tx").locator(".ml-w.is-sel")).toHaveCount(1);
    await expect(w).toHaveClass(/is-sel/);
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
