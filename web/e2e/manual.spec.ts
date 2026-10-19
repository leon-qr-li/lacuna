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

  test("select by dragging across transcript words", async ({ page }) => {
    await open(page);
    const words = page.getByTestId("ml-words").locator(".ml-w");
    await expect(words.nth(5)).toBeVisible();
    const a = (await words.nth(1).boundingBox())!;
    const b = (await words.nth(4).boundingBox())!;
    await page.mouse.move(a.x + 3, a.y + a.height / 2);
    await page.mouse.down();
    await page.mouse.move(b.x + 3, b.y + b.height / 2, { steps: 6 });
    await page.mouse.up();
    await expect(page.getByTestId("ml-bar")).toBeVisible();
    await expect(page.getByTestId("ml-words").locator(".ml-w.is-sel")).toHaveCount(4);
    await page.getByRole("button", { name: /取消/ }).click();
    await expect(page.getByTestId("ml-bar")).toBeHidden();
  });
});
