import { expect, test, type Page } from "@playwright/test";

// The bubble tour of LACUNA 示例节目 (new-user batch, tour v3), all the way: every step is done the way a new
// person does it (the lit part only), and the end shows before / after. Also: the mask blocks the rest of the
// page, and the two sentences the tour fills in are answered without the AI.
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

/** drag on a host's lane over [a, b] (timeline seconds) */
async function drag(page: Page, host: string, a: number, b: number) {
  const lanes = page.getByTestId("edit-lanes");
  const t0 = Number(await lanes.getAttribute("data-start"));
  const span = Number(await lanes.getAttribute("data-span"));
  const r = (await page.getByTestId(`lane-${host}`).boundingBox())!;
  const x = (s: number) => r.x + ((s - t0) / span) * r.width;
  await page.mouse.move(x(a) - 2, r.y + r.height / 2);
  await page.mouse.down();
  await page.mouse.move(x(b) + 2, r.y + r.height / 2, { steps: 6 });
  await page.mouse.up();
}

test("the whole tour, step by step, ends with before / after", async ({ page }) => {
  test.setTimeout(240_000);
  // zoomed in on the timeline, as Leon was (2026-10-23): the tour still brings every spot into view
  await page.addInitScript(() => localStorage.setItem("lacuna.manual.span", "4"));
  await newcomer(page);
  const tour = page.getByTestId("tour");
  const ok = () => page.getByTestId("tour-ok").click();
  const marks = async () => (await page.request.get("/api/episodes/SAMPLE_01/tour/marks")).json();
  const seen: string[] = [];
  for (let guard = 0; guard < 100; guard++) {
    const s = (await tour.getAttribute("data-step"))!;
    seen.push(s);
    if (s === "done") break;
    const m = await marks();
    await page.waitForTimeout(400); // as a person would: after the step's own moves (seek, scroll, open)
    switch (s) {
      case "raw":
        await page.getByTestId("tour-raw-play").click();
        await expect.poll(() => page.getByTestId("tour-raw-audio").evaluate((a: HTMLAudioElement) => a.currentTime)).toBeGreaterThan(0.1);
        // whatever plays can be stopped from the pill (the page itself is masked)
        await page.getByTestId("tour-pause").click();
        await expect.poll(() => page.getByTestId("tour-raw-audio").evaluate((a: HTMLAudioElement) => a.paused)).toBe(true);
        await expect(page.getByTestId("tour-pause")).toHaveCount(0);
        await ok();
        break;
      case "rab":
        // locked: a click outside the lit part lands on the mask
        await page.getByRole("button", { name: /^保留/ }).click({ force: true });
        expect((await (await page.request.get("/api/episodes/SAMPLE_01")).json()).pending_review).toBe(3);
        await page.locator(".rv-act .ab-opt").nth(0).click();
        await page.locator(".rv-act .ab-opt").nth(1).click();
        break;
      case "rdecide":
        for (let i = 0; i < 3; i++) {
          await page.getByRole("button", { name: /^保留/ }).click();
          await expect(page.getByTestId("review-count")).toContainText(`${i + 1} / 3`);
        }
        break;
      case "rnext":
      case "mnext":
      case "vnext":
      case "unext":
        await page.getByTestId("next-step").click();
        break;
      case "lpop": {
        const box = (await page.getByTestId("tour-box").boundingBox())!;
        await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
        await page.getByTestId("ml-pop").getByRole("button", { name: "恢复" }).click();
        break;
      }
      case "lnear":
        await page.getByTestId("tab-near").click();
        break;
      case "cprompt":
        await expect(page.locator("form.chat-form textarea")).toHaveValue("把阿乔问演员名字的那两句删掉");
        await ok();
        break;
      case "csend":
        await page.locator("form.chat-form button.btn-primary").click();
        break;
      case "cab":
        await page.getByTestId("proposal").getByRole("button", { name: "试听前后对比" }).click();
        await page.getByTestId("proposal").locator(".ab button").nth(0).click();
        await page.getByTestId("proposal").locator(".ab button").nth(1).click();
        break;
      case "cok":
        await page.getByTestId("proposal").getByRole("button", { name: "批准" }).click();
        break;
      case "dlanes":
        // LACUNA selects the water line and cuts it itself; the person only reads along
        await expect(page.getByTestId("ml-sel")).toBeVisible();
        await ok();
        break;
      case "dcut":
        await expect(page.getByTestId("ml-sel")).toHaveCount(0);
        await ok();
        break;
      case "mlanes":
        await expect(page.getByTestId("tour-box")).toBeVisible();
        await drag(page, m.hosts[0], m.cough[0] - 0.05, m.cough[1] + 0.05);
        break;
      case "mmute":
        await page.getByTestId("ml-menu").getByTestId(`ml-mute-${m.hosts[0]}`).click();
        break;
      case "vauto":
        await page.getByTestId("levels-auto").click();
        break;
      case "uintro":
        await page.locator('[data-tour="music-asset-intro"]').getByRole("button", { name: "放到 ▾" }).click();
        await page.getByRole("menuitem", { name: /^片头/ }).click();
        break;
      case "uoutro":
        await page.locator('[data-tour="music-asset-outro"]').getByRole("button", { name: "放到 ▾" }).click();
        await page.getByRole("menuitem", { name: /^片尾/ }).click();
        break;
      case "udot": {
        const d = (await page.locator('[data-role="intro"] [data-testid="curve-dot-low"]').boundingBox())!;
        await page.mouse.move(d.x + d.width / 2, d.y + d.height / 2);
        await page.mouse.down();
        await page.mouse.move(d.x + d.width / 2, d.y + d.height / 2 + 20, { steps: 4 });
        await page.mouse.up();
        break;
      }
      case "utry":
        await page.locator('[data-role="intro"] [data-tour="music-try"]').click();
        break;
      case "usend":
        await expect(page.locator('[data-tour="music-assist"] textarea')).toHaveValue("说话时片头音乐再小一点");
        await page.locator('[data-tour="music-assist"]').getByRole("button", { name: "发送" }).click();
        break;
      case "uadopt":
        await page.getByTestId("music-draft").getByRole("button", { name: "采用" }).click();
        break;
      case "xstart":
        await page.getByTestId("export-start").click();
        break;
      case "xdl": {
        const dl = page.waitForEvent("download");
        await page.locator('[data-tour="export-download"] a[download]').first().click();
        await dl;
        break;
      }
      default:
        await ok();
    }
    await expect(tour).not.toHaveAttribute("data-step", s, { timeout: 30_000 });
  }
  // every step was shown once, in order, and nothing was skipped
  expect(seen.length).toBeGreaterThan(55);
  expect(new Set(seen).size).toBe(seen.length);
  const done = page.getByTestId("tour-done");
  await expect(done).toContainText("你审阅了 3 处");
  await expect(done).toContainText("你动手剪了 3 处");
  await expect(done).toContainText("配乐 2 段");
  await done.getByTestId("tour-after").click();
  // the edits the tour made are real: the actor lines, the water line and the cough are gone
  const ep = await (await page.request.get("/api/episodes/SAMPLE_01")).json();
  expect(ep.edits.filter((e: { source: string }) => e.source === "chat")).toHaveLength(1);
  expect(ep.edits.filter((e: { source: string; tracks: string[] | null }) => e.source === "manual" && e.tracks?.length === 1)).toHaveLength(1);
  expect((await (await page.request.get("/api/onboarding")).json()).tour).toBe("done");
  await done.getByTestId("tour-publish").click();
  await expect(page).toHaveURL(/SAMPLE_01\/publish/);
  await expect(page.getByTestId("tour-again")).toBeVisible();
});
