import { expect, test, type Page } from "@playwright/test";

// The bubble tour of LACUNA 示例节目 (new-user batch, tour v3), all the way. A locked demo (Leon 2026-10-23):
// LACUNA does every step itself and the person only presses 知道了; the end shows before / after. Also: the
// mask blocks the whole page, and the sentences, show notes and covers come without the AI.
const PW = "correct horse battery";

test.describe.configure({ mode: "serial" });
test.beforeAll(async ({ request }) => {
  await request.post("/api/auth/_test/reset?skip_setup=false");
});
test.afterAll(async ({ request }) => {
  await request.post("/api/auth/_test/reset?skip_setup=true");
});

async function newcomer(page: Page) {
  expect((await page.request.post("/api/auth/register", { data: { email: "leon@example.com", password: PW, name: "Leon" } })).ok()).toBeTruthy();
  const inv = await (await page.request.post("/api/auth/invites", { data: { email: "tia@example.com", plan: "basic" } })).json();
  await page.context().clearCookies();
  await page.goto(inv.link);
  await page.getByTestId("auth-name").fill("Tia");
  await page.getByTestId("auth-password").fill(PW);
  await page.getByTestId("auth-password2").fill(PW);
  await page.getByRole("button", { name: "创建账号" }).click();
  await page.getByTestId("welcome-sample").click();
  await expect(page).toHaveURL(/SAMPLE_01\/review/);
}

test("the whole tour, step by step, ends with before / after", async ({ page }) => {
  test.setTimeout(240_000);
  // zoomed in on the timeline, as Leon was (2026-10-23): the tour still brings every spot into view
  await page.addInitScript(() => localStorage.setItem("lacuna.manual.span", "4"));
  await newcomer(page);
  const tour = page.getByTestId("tour");
  const ok = () => page.getByTestId("tour-ok").click();
  const seen: string[] = [];
  // LACUNA acts only after 知道了; then the next step comes, or 知道了 again: the step's result, or, before
  // another page, the bubble saying LACUNA will click 下一步 (it clicks only after that 知道了)
  const phase = () => tour.getAttribute("data-phase");
  const moved = (s: string, from = "read") =>
    expect
      .poll(async () => (await tour.getAttribute("data-step")) !== s || ((await phase()) !== from && ["result", "nav"].includes((await phase())!)), { timeout: 60_000 })
      .toBe(true);
  let navs = 0;
  for (let guard = 0; guard < 40; guard++) {
    const s = (await tour.getAttribute("data-step"))!;
    seen.push(s);
    if (s === "done") break;
    if (s === "raw") {
      // the one step without 知道了: nothing plays until the person presses play, the only control
      await expect(tour).toHaveAttribute("data-phase", "read");
      await expect(page.getByTestId("tour-raw").getByTestId("tour-ok")).toHaveCount(0);
      await page.waitForTimeout(800);
      expect(await page.getByTestId("tour-raw-audio").evaluate((a: HTMLAudioElement) => a.paused)).toBe(true);
      await page.getByTestId("tour-raw-play").click();
      await expect.poll(() => page.getByTestId("tour-raw-audio").evaluate((a: HTMLAudioElement) => a.currentTime)).toBeGreaterThan(0.1);
      // whatever plays can be stopped from the pill (the page itself is masked)
      await page.getByTestId("tour-pause").click();
      // paused (or played to the end) → the tour moves on by itself
      await moved(s);
      continue;
    }
    // read first: the bubble is up and nothing has been done yet
    await expect(page.getByTestId("tour-bubble")).toBeVisible();
    await expect(tour).toHaveAttribute("data-phase", "read");
    if (s === "rlist") {
      // locked: even the lit part lands on the mask
      await page.getByTestId("review-list").click({ force: true });
      await page.getByRole("button", { name: /^保留/ }).click({ force: true });
      expect((await (await page.request.get("/api/episodes/SAMPLE_01")).json()).pending_review).toBe(3);
    }
    if (s === "usend") {
      // the request is about the intro, so the intro's curve is the one shown
      await expect(page.locator('[data-testid="placement"][data-role="intro"] [data-testid="music-curve"]')).toBeVisible();
    }
    if (s === "csend") {
      await page.waitForTimeout(1000);
      await expect(page.locator("form.chat-form textarea")).toHaveValue("");
    }
    await ok();
    await moved(s);
    while ((await tour.getAttribute("data-step")) === s) {
      const was = (await phase())!;
      await expect(page.getByTestId("tour-ok")).toBeVisible();
      if (was === "result" && s === "cab") {
        // the new orange cut line shows: no black playhead on top of it
        await expect(page.locator(".mark-cut")).not.toHaveCount(0);
        for (const l of await page.locator(".ml-head-line").all()) await expect(l).toBeHidden();
      }
      if (was === "result" && s === "usend") await expect(page.locator('[data-testid="placement"][data-role="intro"] [data-testid="music-curve"]')).toBeVisible();
      if (was === "nav") {
        navs++;
        await expect(page.getByTestId("tour-bubble")).toContainText("这一部分看完了");
        await expect(page.getByTestId("tour-bubble")).toContainText("按 知道了，LACUNA 点");
      }
      await ok();
      await moved(s, was);
    }
  }
  expect(navs).toBe(6); // review → listen → levels → music → export → publish → poster
  // every step was shown once, in order, and nothing was skipped
  expect(seen.length).toBe(16); // 15 steps, then done
  expect(new Set(seen).size).toBe(seen.length);
  const done = page.getByTestId("tour-done");
  await expect(done).toContainText("审阅了 3 处");
  await expect(done).toContainText("手动剪了 3 处");
  await expect(done).toContainText("配乐 2 段");
  await done.getByTestId("tour-after").click();
  // the edits the tour made are real: the actor lines (chat), the water line (transcript) and the dead air
  // after it (timeline) are gone
  const ep = await (await page.request.get("/api/episodes/SAMPLE_01")).json();
  expect(ep.edits.filter((e: { source: string }) => e.source === "chat")).toHaveLength(1);
  expect(ep.edits.filter((e: { source: string; tracks: string[] | null }) => e.source === "manual" && !e.tracks?.length)).toHaveLength(2);
  expect((await (await page.request.get("/api/onboarding")).json()).tour).toBe("done");
  await done.getByTestId("tour-try").click();
  await expect(page).toHaveURL(/SAMPLE_01\/listen/);
  await expect(page.getByTestId("tour-again")).toBeVisible();
});
