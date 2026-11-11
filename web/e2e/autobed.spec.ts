import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";

// 自动铺底 (docs/decisions/2026-10-30-auto-bed.md): tick songs on 配乐, they fill the free talk at random,
// as a suggestion that is heard before it is accepted.
const INBOX = join(dirname(fileURLToPath(import.meta.url)), ".fixtures", "music_inbox");
const EP = encodeURIComponent("EP_TEST_合成");
const added: string[] = [];

test.afterEach(async ({ request }) => {
  const m = await (await request.get(`/api/episodes/${EP}/music`)).json();
  if (m.draft) await request.post(`/api/episodes/${EP}/music/draft/discard`);
  for (const p of m.placements) if (p.source === "autobed") await request.delete(`/api/episodes/${EP}/music/${p.id}`);
  for (const id of added.splice(0)) await request.delete(`/api/library/assets/${id}`);
});

test("autobed: tick songs, each goes in once, straight onto the episode; remove all", async ({ page }) => {
  const r = await page.request.post(`/api/library/upload?${new URLSearchParams({ name: "odyssey_theme.mp3", kind: "bed", note: "" })}`, {
    headers: { "Content-Type": "application/octet-stream" },
    data: readFileSync(join(INBOX, "odyssey_theme.mp3")),
  });
  expect(r.ok()).toBeTruthy();
  const j = await r.json();
  if (!j.duplicate) added.push(j.asset.id);
  await page.request.patch(`/api/library/assets/${j.asset.id}`, { data: { kind: "bed" } });
  await page.goto(`/#/ep/${EP}/music`);
  await page.getByTestId("autobed-open").click();
  const card = page.getByTestId("autobed");
  await expect(card.getByTestId("autobed-meter")).toContainText("还空着");
  const row = card.locator("li", { hasText: "odyssey_theme" });
  await expect(row.getByTestId("autobed-song")).toBeChecked(); // 聊天背景音 is ticked by default
  await expect(card.getByTestId("autobed-fill")).toContainText("铺上勾的");
  await card.getByTestId("autobed-fill").click();
  // straight onto the episode: no suggestion to accept; each ticked song once
  await expect(page.getByTestId("music-msg")).toContainText("铺好了");
  await expect(page.getByTestId("music-draft")).toHaveCount(0);
  let m = await (await page.request.get(`/api/episodes/${EP}/music`)).json();
  const beds = m.placements.filter((p: { source?: string; role: string }) => p.source === "autobed" && p.role === "bed");
  expect(beds.length).toBe(1);
  await expect(card.getByTestId("autobed-fill")).toHaveText("换个随机位置");
  // 取消所有铺底
  await card.getByTestId("autobed-clear").click();
  await page.getByTestId("dialog").getByRole("button", { name: "取消所有铺底" }).click();
  await expect(page.getByTestId("music-msg")).toContainText("取消了");
  m = await (await page.request.get(`/api/episodes/${EP}/music`)).json();
  expect(m.placements.some((p: { role: string }) => p.role === "bed")).toBeFalsy();
});
