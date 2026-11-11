import { expect, test, type Page } from "@playwright/test";
import { SCOPES_PORT } from "../playwright.config";
import { undoKey } from "./undo";

// Leon 2026-10-30, on the cloud site: 删除这段 hung and every edit button stayed grey until a refresh (and then the
// word was gone: the cut was made, its answer lost); past 4:45 the waveform stayed empty until he switched pages;
// 整集试听 opened where 审阅 had been; a refresh forgot where he was editing. Runs on the scopes server.
test.use({ baseURL: `http://127.0.0.1:${SCOPES_PORT}` });
const EP = "EP_TEST_合成";
const listen = `/#/ep/${encodeURIComponent(EP)}/listen`;

async function open(page: Page) {
  await page.goto(listen);
  await expect(page.getByTestId("edit-lanes")).toBeVisible();
  await expect(page.getByTestId("lane-Leon").locator("canvas")).toBeVisible();
}

const clock = async (page: Page) => ((await page.getByTestId("clock").textContent()) ?? "").split("/")[0].trim();

test.describe.serial("editing over a bad connection", () => {
  test("a cut whose answer never comes: the buttons come back and the cut shows", async ({ page }) => {
    test.setTimeout(90_000);
    await open(page);
    // the server makes the cut; its answer is lost on the way back (the browser hears nothing at all)
    await page.route(
      (u) => u.pathname.endsWith("/manual/cut"),
      async (route) => {
        await route.fetch();
        await new Promise((r) => setTimeout(r, 30_000));
        await route.abort().catch(() => undefined);
      },
    );
    const w = page.getByTestId("ml-tx").locator(".ml-w").nth(8);
    await w.click();
    const cut = page.getByTestId("transcript-edit").getByTestId("ml-cut");
    await cut.click();
    await expect(page.locator(".toast")).toContainText("网络断了一下", { timeout: 30_000 });
    // what the server has now is on screen: the word is struck, no refresh needed
    await expect(page.getByTestId("ml-tx").locator("s.ml-gone[data-edit^='m']")).not.toHaveCount(0);
    await page.unroute((u) => u.pathname.endsWith("/manual/cut"));
    // and the edit buttons work again
    await page.getByTestId("ml-tx").locator(".ml-w").nth(14).click();
    await expect(cut).toBeEnabled();
    await undoKey(page);
    await expect(page.locator(".toast")).toContainText("已撤销");
  });

  test("waveform tiles that got no answer are asked for again", async ({ page }) => {
    const tries = new Map<string, number>();
    await page.route(
      (u) => u.pathname.endsWith("/manual/wave"),
      async (route) => {
        const tile = new URL(route.request().url()).searchParams.get("tile")!;
        tries.set(tile, (tries.get(tile) ?? 0) + 1);
        if (tries.get(tile) === 1) return route.abort("failed");
        return route.fallback();
      },
    );
    const answered = page.waitForResponse((r) => r.url().includes("/manual/wave") && r.url().includes("tile=0") && r.ok());
    await page.goto(listen);
    await expect(page.getByTestId("edit-lanes")).toBeVisible();
    await answered;
    expect(tries.get("0")).toBeGreaterThanOrEqual(2);
  });

  test("整集试听 remembers the editing place; from 审阅 it starts from the beginning", async ({ page }) => {
    await page.goto("/");
    await page.evaluate((ep) => localStorage.removeItem(`lacuna.pos.${ep}`), EP);
    await open(page);
    await expect.poll(() => clock(page)).toBe("0:00");
    await page.getByTestId("lane-Pei").click({ position: { x: 300, y: 20 } }); // a click seeks
    await expect.poll(() => clock(page)).not.toBe("0:00");
    const here = await clock(page);
    // a refresh comes back to the same place
    await page.reload();
    await expect(page.getByTestId("edit-lanes")).toBeVisible();
    await expect.poll(() => clock(page)).toBe(here);
    // leaving the episode and coming back: still there
    await page.goto("/#/");
    await open(page);
    await expect.poll(() => clock(page)).toBe(here);
    // another tab (配乐) and back: still there
    await page.goto(`/#/ep/${encodeURIComponent(EP)}/music`);
    await page.goto(listen);
    await expect(page.getByTestId("edit-lanes")).toBeVisible();
    await expect.poll(() => clock(page)).toBe(here);
    // 审阅 at 0:50, then 整集试听: from the beginning, not 审阅's place
    await page.goto(`/#/ep/${encodeURIComponent(EP)}/review`);
    await page.getByTestId("main-audio").evaluate((a: HTMLAudioElement) => (a.currentTime = 50));
    await expect.poll(() => clock(page)).toBe("0:50");
    await page.goto(listen);
    await expect(page.getByTestId("edit-lanes")).toBeVisible();
    await expect.poll(() => clock(page)).toBe("0:00");
    // and a refresh there keeps that
    await page.reload();
    await expect(page.getByTestId("edit-lanes")).toBeVisible();
    await expect.poll(() => clock(page)).toBe("0:00");
  });
});
