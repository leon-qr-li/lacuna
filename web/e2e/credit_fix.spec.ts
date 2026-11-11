import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import type { APIRequestContext } from "@playwright/test";
import { SCOPES_PORT } from "../playwright.config";

// 一键修复曲名和作者 (features/credit-fix, decision 2026-10-30-credit-fix) on the library-scopes server, whose
// fake lookup (tests/app/fake_credit_fix.py) finds "Theme <name>", gives "alt" two candidates and can't place "乱码".
test.use({ baseURL: `http://127.0.0.1:${SCOPES_PORT}` });

const INBOX = join(dirname(fileURLToPath(import.meta.url)), ".fixtures", "music_inbox");
const EP = "EP_TEST_合成";

type Asset = { id: string; name: string; credit: { title: string | null; composer: string | null; status: string } };

/** A short silent WAV; the length makes each file a different asset. */
function wav(seconds: number): Buffer {
  const sr = 8000;
  const n = Math.round(sr * seconds);
  const b = Buffer.alloc(44 + n * 2);
  b.write("RIFF", 0);
  b.writeUInt32LE(36 + n * 2, 4);
  b.write("WAVEfmt ", 8);
  b.writeUInt32LE(16, 16);
  b.writeUInt16LE(1, 20);
  b.writeUInt16LE(1, 22);
  b.writeUInt32LE(sr, 24);
  b.writeUInt32LE(sr * 2, 28);
  b.writeUInt16LE(2, 32);
  b.writeUInt16LE(16, 34);
  b.write("data", 36);
  b.writeUInt32LE(n * 2, 40);
  for (let i = 0; i < n; i++) b.writeInt16LE(Math.round(800 * Math.sin((i * 2 * Math.PI * 220) / sr)), 44 + i * 2);
  return b;
}

async function upload(request: APIRequestContext, name: string, data: Buffer, episode = "") {
  const q = new URLSearchParams({ name, kind: "interlude", note: "" });
  if (episode) q.set("episode", episode);
  const r = await request.post(`/api/library/upload?${q}`, { headers: { "Content-Type": "application/octet-stream" }, data });
  expect(r.ok()).toBeTruthy();
}

test.beforeEach(async ({ request }) => {
  for (const a of (await (await request.get("/api/library")).json()).assets as Asset[]) await request.delete(`/api/library/assets/${a.id}`);
  await request.delete(`/api/library/credit-fix?${new URLSearchParams({ episode: EP })}`);
  await request.delete("/api/library/credit-fix");
});

test("music page: one click fixes this episode's own tracks after a look", async ({ page }) => {
  await upload(page.request, "odyssey_theme.mp3", readFileSync(join(INBOX, "odyssey_theme.mp3"))); // shared: not touched
  await upload(page.request, "bgm_final.wav", wav(2.1), EP);
  await upload(page.request, "alt.wav", wav(2.3), EP);
  await upload(page.request, "乱码.wav", wav(2.5), EP);

  await page.goto(`/#/ep/${encodeURIComponent(EP)}/music`);
  const lib = page.getByTestId("music-library");
  await expect(lib.getByTestId("music-asset").filter({ hasText: "bgm_final" })).toContainText("还不知道作者");
  const button = lib.getByTestId("credit-fix-list");
  await expect(button).toHaveClass(/is-hot/);
  await button.click();

  const dlg = page.getByTestId("credit-fix-dialog");
  await expect(dlg).toContainText("这次修这一集的 3 首歌");
  await expect(dlg).not.toContainText("odyssey_theme");
  await dlg.getByTestId("credit-fix-prompt").fill("全是《午夜凶铃》原声");
  await dlg.getByTestId("credit-fix-start").click();
  await expect(dlg.getByTestId("credit-fix-running")).toBeVisible();
  // closing doesn't stop it; the button says when it's done
  await dlg.getByRole("button", { name: "先关掉" }).click();
  await expect(button).toContainText("曲名查好了，去看看", { timeout: 15_000 });
  await button.click();

  const rows = dlg.getByTestId("credit-fix-row");
  await expect(rows).toHaveCount(3);
  const found = rows.filter({ hasText: "bgm_final.wav" });
  await expect(found).toContainText("“Theme bgm_final”");
  await expect(found).toContainText("川井宪次 · 《午夜凶铃》原声 · 1998");
  await expect(found.getByRole("checkbox")).toBeChecked();
  const alt = rows.filter({ hasText: "alt.wav" });
  await expect(alt.getByRole("checkbox")).not.toBeChecked();
  await alt.getByRole("button", { name: "换成：Video Tape — 川井宪次" }).click();
  await expect(alt).toContainText("“Video Tape”");
  await expect(alt.getByRole("checkbox")).toBeChecked();
  const none = rows.filter({ hasText: "乱码.wav" });
  await expect(none).toContainText("没查到，原来的名字不动");
  await expect(none.getByRole("checkbox")).toBeDisabled();
  // a field fixed by hand before applying
  await found.getByRole("button", { name: "自己改" }).click();
  await found.getByLabel("年份").fill("1999");
  await dlg.getByTestId("credit-fix-apply").click();
  await expect(dlg).toHaveCount(0);
  await expect(page.getByText("已更新 2 首的曲名和作者")).toBeVisible();

  // the list shows 作者 · 出处 under the new title; the BGM credits use it; shared music untouched
  const row = lib.getByTestId("music-asset").filter({ hasText: "Theme bgm_final" });
  await expect(row).toContainText("川井宪次 · 《午夜凶铃》原声");
  await expect(lib.getByTestId("music-asset").filter({ hasText: "Video Tape" })).toBeVisible();
  const assets = (await (await page.request.get("/api/library")).json()).assets as Asset[];
  const by = Object.fromEntries(assets.map((a) => [a.name, a.credit]));
  expect(by["bgm_final.wav"].status).toBe("confirmed");
  expect(by["alt.wav"].title).toBe("Video Tape");
  expect(by["乱码.wav"].status).toBe("unknown");
  expect(by["odyssey_theme.mp3"].status).not.toBe("confirmed");
  // one left without a confirmed title: the button still asks for attention
  await expect(button).toHaveClass(/is-hot/);
});

test("library page: the same button covers the shared music; nothing changes on 都不要", async ({ page }) => {
  await upload(page.request, "odyssey_theme.mp3", readFileSync(join(INBOX, "odyssey_theme.mp3")));
  await upload(page.request, "bgm_final.wav", wav(2.1), EP); // this episode's own: the music page's job
  await page.goto("/#/library");
  await page.getByTestId("credit-fix").click();
  const dlg = page.getByTestId("credit-fix-dialog");
  await expect(dlg).toContainText("这次修共用的 1 首歌");
  await expect(dlg).toContainText("odyssey_theme.mp3");
  await expect(dlg).not.toContainText("bgm_final");
  await dlg.getByTestId("credit-fix-start").click();
  await expect(dlg.getByTestId("credit-fix-row")).toHaveCount(1, { timeout: 15_000 });
  await dlg.getByTestId("credit-fix-discard").click();
  await expect(dlg).toHaveCount(0);
  const assets = (await (await page.request.get("/api/library")).json()).assets as Asset[];
  expect(assets.find((a) => a.name === "odyssey_theme.mp3")!.credit.title).toBe("Odyssey Main Theme");
});
