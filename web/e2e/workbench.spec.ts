import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

// Leon 2026-10-20 (version B): 整集试听 is one screen — the timeline (minimap + player inside) on top, the transcript
// under it, a side panel with tabs AI 制作人 / 这附近改了什么; 「下一步」 at the top right of every step.

async function openListen(page: Page) {
  await page.goto("/");
  await expect(page).toHaveURL(/#\/ep\/.+\/listen/, { timeout: 20_000 });
  await expect(page.getByTestId("lane-Leon").locator("canvas")).toBeVisible();
}

test("整集试听 fits one screen: timeline, player and transcript all in view, no page scroll", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openListen(page);
  const scroll = await page.evaluate(() => document.scrollingElement!.scrollHeight - window.innerHeight);
  expect(scroll).toBeLessThanOrEqual(1);
  const lanes = (await page.getByTestId("edit-lanes").boundingBox())!;
  const tx = (await page.getByTestId("transcript-edit").boundingBox())!;
  const player = (await page.getByRole("region", { name: "播放器" }).boundingBox())!;
  expect(tx.y).toBeGreaterThan(lanes.y + lanes.height - 1); // transcript under the timeline
  expect(tx.y + tx.height).toBeLessThanOrEqual(900);
  // the player and the minimap live inside the timeline card
  expect(player.y).toBeGreaterThan(lanes.y);
  expect(player.y + player.height).toBeLessThanOrEqual(lanes.y + lanes.height);
  const mini = (await page.getByTestId("minimap").boundingBox())!;
  expect(mini.y).toBeGreaterThan(lanes.y);
  expect(mini.y).toBeLessThan((await page.getByTestId("ml-ruler").boundingBox())!.y);
  // each lane is taller than the old 44 px strip
  expect((await page.getByTestId("lane-Leon").boundingBox())!.height).toBeGreaterThan(56);
  // the transcript scrolls inside its own card
  const inner = await page.getByTestId("ml-tx").evaluate((el) => el.scrollHeight > el.clientHeight && getComputedStyle(el).overflowY);
  expect(inner).toBe("auto");
  // no separate overview card any more, and no 下一步 at the page bottom
  await expect(page.getByRole("region", { name: "整集概览" })).toHaveCount(0);
  await expect(page.locator(".next-step")).toHaveCount(0);
});

test("minimap: a click moves the playhead", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openListen(page);
  const m = (await page.getByTestId("minimap").boundingBox())!;
  await page.mouse.click(m.x + m.width * 0.5, m.y + m.height / 2);
  await expect(page.getByTestId("clock")).not.toContainText(/^0:00 /);
});

test("side panel: tabs AI 制作人 / 这附近改了什么, counted, remembered", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openListen(page);
  const chat = page.getByRole("region", { name: "AI 制作人对话" });
  await expect(page.getByTestId("tab-ai")).toHaveAttribute("aria-selected", "true");
  await expect(page.getByTestId("editor-badge")).toBeVisible();
  await expect(page.getByTestId("chat-log")).toBeVisible();
  await expect(page.getByTestId("nearby")).toHaveCount(0);

  // jump to an edit so the nearby list has rows
  const m = (await page.getByTestId("minimap").boundingBox())!;
  await page.mouse.click(m.x + m.width * 0.35, m.y + m.height / 2);
  await page.getByTestId("tab-near").click();
  await expect(page.getByTestId("tab-near")).toHaveAttribute("aria-selected", "true");
  await expect(page.getByTestId("chat-log")).toBeHidden();
  await expect(page.getByLabel(/对 AI 制作人说/)).toBeHidden();
  const rows = page.locator("[data-testid=nearby] li");
  await expect(rows.first()).toBeVisible();
  await expect(page.getByTestId("tab-near").locator(".side-n")).toHaveText(String(await rows.count()));
  // 收起 stays at the panel's top right
  const cb = (await chat.getByRole("button", { name: "收起" }).boundingBox())!;
  const pb = (await chat.boundingBox())!;
  expect(pb.x + pb.width - (cb.x + cb.width)).toBeLessThan(40);

  await page.reload();
  await expect(page.getByTestId("tab-near")).toHaveAttribute("aria-selected", "true", { timeout: 20_000 });
  await page.getByTestId("tab-ai").click();
  await expect(page.getByTestId("chat-log")).toBeVisible();
});

test("timeline: the card on a cut listens around it and restores it, undo puts it back", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openListen(page);
  const lane = page.getByTestId("lane-Leon");
  const lb = (await lane.boundingBox())!;
  const cut = (await lane.locator(".mark-cut").first().boundingBox())!;
  await page.mouse.move(cut.x + cut.width / 2 + 2, lb.y + lb.height / 2);
  const pop = page.getByTestId("ml-pop");
  await expect(pop).toBeVisible();
  await expect(lane.locator(".mark-cut").first()).not.toHaveAttribute("title", /.+/); // no native tooltip on top of it
  // the card stays while the pointer moves onto it
  const pb = (await pop.boundingBox())!;
  await page.mouse.move(cut.x + 2, pb.y + 4, { steps: 4 });
  await page.mouse.move(pb.x + pb.width / 2, pb.y + pb.height / 2, { steps: 4 });
  await expect(pop).toBeVisible();

  await pop.getByRole("button", { name: /听前后/ }).click();
  await expect.poll(() => page.getByTestId("main-audio").evaluate((a: HTMLAudioElement) => !a.paused)).toBe(true);
  await page.getByTestId("play").click(); // pause

  const before = await lane.locator(".mark-cut").count();
  await pop.getByRole("button", { name: "恢复" }).click();
  await expect(page.locator(".toast")).toContainText("已恢复原话");
  await expect.poll(() => lane.locator(".mark-cut").count()).toBeLessThan(before);
  await page.getByRole("button", { name: "撤销" }).click();
  await expect(page.locator(".toast")).toContainText("已撤销");
  await expect.poll(() => lane.locator(".mark-cut").count()).toBe(before);

  // away from the marks the card goes
  await page.mouse.move(10, 10);
  await expect(pop).toBeHidden();
});

test("下一步 sits at the top right on every step, after 导出", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openListen(page);
  const steps = await page.getByRole("navigation", { name: "制作流程" }).getByRole("link").evaluateAll((as) => as.map((a) => a.getAttribute("href")!));
  const pages = [...steps];
  for (const h of steps) {
    await page.goto("/" + h);
    for (const s of await page.locator("nav.subtabs a").evaluateAll((as) => as.map((a) => a.getAttribute("href")!))) if (!pages.includes(s)) pages.push(s);
  }
  let withNext = 0;
  for (const h of pages) {
    await page.goto("/" + h);
    await expect(page.getByRole("navigation", { name: "制作流程" })).toBeVisible();
    await expect(page.locator(".next-step")).toHaveCount(0);
    const next = page.getByTestId("next-step");
    if (!(await next.count())) continue;
    withNext++;
    const b = (await next.boundingBox())!;
    expect(b.y).toBeLessThan(140);
    expect(1440 - (b.x + b.width)).toBeLessThan(60);
    await expect(page.locator(".ep-head-row > :last-child")).toHaveAttribute("data-testid", "next-step");
  }
  expect(withNext).toBe(pages.length - 1); // every page but the last one
});

test("English: the tabs and 收起 fit the side panel; the header does not overlap", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("lacuna.lang", "en"));
  await page.setViewportSize({ width: 1440, height: 900 });
  await openListen(page);
  const chat = page.getByRole("region", { name: "AI producer chat" });
  const near = (await page.getByTestId("tab-near").boundingBox())!;
  const col = (await chat.getByTestId("chat-collapse").boundingBox())!;
  const pb = (await chat.boundingBox())!;
  expect(near.x + near.width).toBeLessThanOrEqual(col.x);
  expect(col.x + col.width).toBeLessThanOrEqual(pb.x + pb.width);
  const nav = (await page.getByRole("navigation", { name: "Production steps" }).boundingBox())!;
  const nx = (await page.getByTestId("next-step").boundingBox())!;
  expect(nx.y + nx.height <= nav.y || nx.x >= nav.x + nav.width).toBe(true);
});
