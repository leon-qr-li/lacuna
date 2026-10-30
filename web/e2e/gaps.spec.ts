import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// 间隙 (docs/decisions/2026-10-30-edit-gaps.md): right-click the timeline or 「＋」 between two lines of the
// transcript opens a gap; the voice cut stays the same, the final mix gets the time; 配乐 fills the gaps;
// an export with empty gaps asks first.
const INBOX = join(dirname(fileURLToPath(import.meta.url)), ".fixtures", "music_inbox");
const EP = encodeURIComponent("EP_TEST_合成");
type Gap = { id: string; voice_s: number; len_s: number; filled_by: string | null };

const gapsOf = async (r: APIRequestContext) => ((await (await r.get(`/api/episodes/${EP}/gaps`)).json()).gaps as Gap[]);
const added: string[] = [];

// leave the shared episode and library as they were, also when a check fails
test.afterEach(async ({ request }) => {
  for (const g of await gapsOf(request)) await request.delete(`/api/episodes/${EP}/gaps/${g.id}`);
  const m = await (await request.get(`/api/episodes/${EP}/music`)).json();
  if (m.draft) await request.post(`/api/episodes/${EP}/music/draft/discard`);
  for (const id of added.splice(0)) await request.delete(`/api/library/assets/${id}`);
});

async function open(page: Page) {
  await page.goto(`/#/ep/${EP}/listen`);
  await expect(page.getByTestId("edit-lanes")).toBeVisible();
  await expect(page.getByTestId("lane-Leon").locator("canvas")).toBeVisible();
}

test("gaps: add on the timeline and the transcript, change, remove; the voice cut stays", async ({ page }) => {
  await open(page);
  const voice = (await (await page.request.get(`/api/episodes/${EP}`)).json()).duration as number;
  const before = (await (await page.request.get(`/api/episodes/${EP}/music`)).json()).duration as number;
  // right-click away from a selection: 「在此处加入间隙」 with a length
  const lane = (await page.getByTestId("lane-Leon").boundingBox())!;
  await page.mouse.click(lane.x + lane.width * 0.5, lane.y + lane.height / 2, { button: "right" });
  const menu = page.getByTestId("gap-menu");
  await expect(menu).toBeVisible();
  await expect(menu.getByRole("menuitem")).toHaveText("在此处加入间隙G");
  await expect(page.getByTestId("ml-menu")).toHaveCount(0);
  await menu.getByTestId("gap-add-5").click();
  await expect(menu).toHaveCount(0);
  const marks = page.getByTestId("gap-mark");
  await expect(marks).toHaveCount(2); // one on each host's lane
  await expect(marks.first()).toHaveText("5 秒");
  expect((await gapsOf(page.request))[0].len_s).toBe(5);
  // its card: another length, then 15 s
  await marks.first().click();
  const card = page.getByTestId("gap-card");
  await expect(card).toContainText("间隙 5 秒");
  await expect(card).toContainText("待配乐");
  await card.getByTestId("gap-set-15").click();
  await expect(marks.first()).toHaveText("15 秒");
  await page.keyboard.press("Escape");
  await expect(card).toHaveCount(0);
  // the transcript shows it between two lines
  await expect(page.getByTestId("gap-row")).toHaveCount(1);
  await expect(page.getByTestId("gap-row")).toContainText("间隙 15 秒");
  // 「＋」 between two other lines adds one with the default 15 s
  await page.getByTestId("gap-plus").first().click();
  await expect.poll(async () => (await gapsOf(page.request)).length).toBe(2);
  await expect(page.getByTestId("gap-row")).toHaveCount(2);
  // the voice cut is as it was; the final mix is 30 s longer
  expect((await (await page.request.get(`/api/episodes/${EP}`)).json()).duration).toBe(voice);
  const m = await (await page.request.get(`/api/episodes/${EP}/music`)).json();
  expect(m.duration).toBeCloseTo(before + 30, 1);
  // 「带配乐听」 is offered: the gaps are heard in the mix
  await expect(page.getByTestId("listen-with-music")).toBeVisible();
  // remove one from the transcript
  await page.getByTestId("gap-row").first().getByTestId("gap-row-edit").click();
  await page.getByTestId("gap-row").first().getByTestId("gap-delete").click();
  await expect(page.getByTestId("gap-row")).toHaveCount(1);
  await expect(marks).toHaveCount((await gapsOf(page.request)).some((g) => g.voice_s <= 30) ? 2 : 0);
});

test("gaps: G adds one at the playhead; an export with empty gaps asks first", async ({ page }) => {
  await open(page);
  await page.getByTestId("edit-lanes").getByRole("heading", { name: "剪辑时间线" }).click();
  await page.keyboard.press("g");
  await expect.poll(async () => (await gapsOf(page.request)).length).toBe(1);
  const job = async () => (await (await page.request.get(`/api/episodes/${EP}/export`)).json()).job?.id ?? null;
  const before = await job();
  await page.goto(`/#/ep/${EP}/export`);
  await page.getByTestId("export-start").click();
  const dlg = page.getByTestId("dialog");
  await expect(dlg).toContainText("还有间隙没配乐");
  await expect(dlg).toContainText("1 个间隙还没配乐");
  await dlg.getByRole("button", { name: "先不导出" }).click();
  await expect(dlg).toHaveCount(0);
  expect(await job()).toBe(before); // no export started
});

test("gaps: 配乐 fills the empty ones with a 休息间隙 piece, heard before it is accepted", async ({ page }) => {
  const r = await page.request.post(`/api/library/upload?${new URLSearchParams({ name: "odyssey_theme.mp3", kind: "interlude", note: "" })}`, {
    headers: { "Content-Type": "application/octet-stream" },
    data: readFileSync(join(INBOX, "odyssey_theme.mp3")),
  });
  expect(r.ok()).toBeTruthy();
  const j = await r.json();
  if (!j.duplicate) added.push(j.asset.id);
  await page.request.patch(`/api/library/assets/${j.asset.id}`, { data: { kind: "interlude" } });
  await page.request.post(`/api/episodes/${EP}/gaps`, { data: { voice_s: 20, len_s: 8 } });
  await page.goto(`/#/ep/${EP}/music`);
  const banner = page.getByTestId("gap-banner");
  await expect(banner).toContainText("这一集有 1 个间隙，1 个还没配乐。");
  await expect(page.getByTestId("mstrip-gap")).toHaveCount(1);
  await banner.getByTestId("gap-fill").click();
  const draft = page.getByTestId("music-draft");
  await expect(draft).toBeVisible();
  await expect(draft.getByTestId("draft-change")).toContainText("的间隙（8 秒）");
  await draft.getByRole("button", { name: "采用" }).click();
  await expect(banner).toContainText("都已经配好音乐");
  await expect(page.getByTestId("gap-fill")).toHaveCount(0);
  await expect(page.getByTestId("mstrip-gap")).toHaveCount(0);
  const g = (await gapsOf(page.request))[0];
  expect(g.filled_by).toBeTruthy();
  await expect(page.getByTestId("placement-plan").first()).toContainText("间隙里");
});
