import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";

// written by tests/app/serve_e2e.py when the backend starts
const INBOX = join(dirname(fileURLToPath(import.meta.url)), ".fixtures", "music_inbox");

const EP = encodeURIComponent("EP_TEST_合成");

// one flow: the music tests share the backend's library and the episode's music
test("media library → credits → music on the episode → series rule", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "素材库" }).click();
  await expect(page).toHaveURL(/#\/library/);
  await expect(page.getByText("素材库还是空的")).toBeVisible();

  // add the theme with the system file picker, then say what it is
  await page.getByLabel("选择音乐文件").setInputFiles(join(INBOX, "odyssey_theme.mp3"));
  await expect(page.getByTestId("uploads")).toContainText("已加入：odyssey_theme.mp3");
  const theme = page.getByTestId("asset-row").filter({ hasText: "odyssey_theme.mp3" });
  await expect(theme).toContainText("待确认"); // from the file's own tags
  // Claude can't hear the music: no note, no lookup
  await expect(theme.getByRole("button", { name: "让 Claude 查正式曲名" })).toBeDisabled();
  await theme.getByLabel("备注").fill("这是奥德赛的主题曲");
  await theme.getByRole("button", { name: "保存备注" }).click();
  await expect(theme.getByRole("button", { name: "保存备注" })).toBeDisabled();
  await expect(theme.getByTestId("credit-line")).toContainText("Odyssey Main Theme");

  // Claude looks up the official title (fake client), Leon confirms it
  await theme.getByRole("button", { name: "让 Claude 查正式曲名" }).click();
  await expect(theme.getByTestId("credit-line")).toContainText("《奥德赛》原声 · Ludwig Göransson — “Odysseus”");
  await expect(theme).toContainText("Claude 查的");
  await expect(theme.getByLabel("曲名")).toHaveValue("Odysseus"); // filled in, ready to correct
  await theme.getByRole("button", { name: "收起" }).click();
  await theme.getByRole("button", { name: "对，就是这首" }).click();
  await expect(theme).toContainText("已确认");

  // the jingle is dragged onto the page as a series intro, then gets a hand-written credit
  await page.getByLabel("新文件的用途").selectOption("intro");
  const bytes = [...readFileSync(join(INBOX, "洛城片头.wav"))];
  const drop = await page.evaluateHandle((b) => {
    const dt = new DataTransfer();
    dt.items.add(new File([new Uint8Array(b)], "洛城片头.wav", { type: "audio/wav" }));
    return dt;
  }, bytes);
  await page.getByTestId("drop-zone").dispatchEvent("dragover", { dataTransfer: drop });
  await expect(page.getByTestId("drop-zone")).toHaveClass(/lib-drop-active/);
  await page.getByTestId("drop-zone").dispatchEvent("drop", { dataTransfer: drop });
  await expect(page.getByTestId("uploads")).toContainText("已加入：洛城片头.wav");
  const jingle = page.getByTestId("asset-row").filter({ hasText: "洛城片头.wav" });
  await expect(jingle.getByLabel("用途")).toHaveValue("intro");

  // the same file again is not added twice
  await page.getByLabel("选择音乐文件").setInputFiles(join(INBOX, "odyssey_theme.mp3"));
  await expect(page.getByTestId("uploads")).toContainText("跳过：odyssey_theme.mp3");
  await expect(page.getByTestId("asset-row")).toHaveCount(2);
  await expect(jingle).toContainText("还不知道曲名");
  await jingle.getByRole("button", { name: "手动改" }).click();
  await jingle.getByLabel("曲名").fill("洛城二三事 片头");
  await jingle.getByRole("button", { name: "保存署名" }).click();
  await expect(jingle.getByTestId("credit-line")).toContainText("“洛城二三事 片头”");
  await expect(jingle).toContainText("已确认");

  // ---- the episode's music tab
  await page.goto(`/#/ep/${EP}/music`);
  await expect(page.getByRole("heading", { name: "配乐", exact: true })).toBeVisible();
  await expect(page.getByText("BGM：未设置")).toBeVisible();
  const voice = await page.getByText(/人声剪辑 .* → 成品 /).innerText();
  await page.getByLabel("选择素材").selectOption({ label: "“洛城二三事 片头” · 片头（播客开始）" });
  await expect(page.getByLabel("用途")).toHaveValue("intro"); // taken from the asset's use
  await page.getByRole("button", { name: "放进去" }).click();
  await expect(page.getByTestId("placement")).toHaveCount(1);
  await expect(page.getByText(/人声剪辑 .* → 成品 /)).not.toHaveText(voice); // the intro adds time

  // an interlude at 0:20 of the final cut
  await page.getByLabel("选择素材").selectOption({ label: "《奥德赛》原声 · Ludwig Göransson — “Odysseus” · 其他素材" });
  await page.getByLabel("用途").selectOption("interlude");
  await page.getByRole("button", { name: "放进去" }).click();
  await expect(page.getByText("请写位置")).toBeVisible();
  await page.getByLabel("位置", { exact: true }).fill("0:20");
  await page.getByRole("button", { name: "放进去" }).click();
  const mid = page.getByTestId("placement").filter({ hasText: "间奏" });
  await expect(mid).toContainText("odyssey_theme.mp3");
  await expect(mid).toContainText("插入");
  const credits = page.getByTestId("credits");
  await expect(credits).toContainText("片头：“洛城二三事 片头”");
  await expect(credits).toContainText("间奏：《奥德赛》原声 · Ludwig Göransson — “Odysseus”");

  // hear the transition, then the whole mix stream
  await mid.getByRole("button", { name: "试听这一处" }).click();
  await expect(mid.getByRole("button", { name: "停止" })).toBeVisible();
  await expect.poll(() => page.getByTestId("placement-audio").evaluate((a: HTMLAudioElement) => a.currentTime)).toBeGreaterThan(0.2);
  await mid.getByRole("button", { name: "停止" }).click();
  const mixUrl = await page.getByTestId("mix-audio").getAttribute("src");
  expect(mixUrl).toMatch(/\/mix\/[0-9a-f]+\.wav$/);
  const head = await page.request.get(mixUrl!, { headers: { Range: "bytes=0-43" } });
  expect(head.status()).toBe(206);

  // gain change is saved
  await mid.getByLabel("音量（dB）").fill("-4");
  await mid.getByRole("button", { name: "保存" }).click();
  await expect(page.getByText("已保存")).toBeVisible();

  // remember the intro as the series rule, then it is offered once the episode has none
  await page.getByRole("button", { name: "记成系列片头片尾" }).click();
  await expect(page.getByText("已记住")).toBeVisible();
  await page.getByTestId("placement").filter({ hasText: "片头" }).getByRole("button", { name: "去掉" }).click();
  await expect(page.getByTestId("series-suggestion")).toContainText("洛城二三事");
  await page.getByRole("button", { name: "用系列片头片尾" }).click();
  await expect(page.getByTestId("placement").filter({ hasText: "片头" })).toHaveCount(1);
  await expect(page.getByTestId("series-suggestion")).toHaveCount(0);

  // leave the shared episode as it was
  for (const name of ["片头", "间奏"]) {
    await page.getByTestId("placement").filter({ hasText: name }).getByRole("button", { name: "去掉" }).click();
  }
  await page.getByRole("button", { name: "这一集不用" }).click();
  await expect(page.getByTestId("placement")).toHaveCount(0);
});

// Music suggestions: music placed by its use, heard as a suggestion first, nudged, and changed by talking to Claude
test("place by use → hear the suggestion → accept → nudge → change it by talking", async ({ page }) => {
  // the theme becomes a break interlude in the library; the jingle is already an intro
  await page.goto("/#/library");
  const theme = page.getByTestId("asset-row").filter({ hasText: "odyssey_theme.mp3" });
  await theme.getByLabel("用途").selectOption("interlude");
  await expect(theme.getByLabel("用途")).toHaveValue("interlude");

  await page.goto(`/#/ep/${EP}/music`);
  await expect(page.getByTestId("placement")).toHaveCount(0);
  await page.getByRole("button", { name: "按用途自动放好" }).click();
  const draft = page.getByTestId("music-draft");
  await expect(draft.getByTestId("draft-change")).toHaveCount(2);
  await expect(draft).toContainText("片头：“洛城二三事 片头”");
  await expect(draft).toContainText("间奏：《奥德赛》原声");
  await expect(page.getByTestId("placement")).toHaveCount(0); // only a suggestion so far
  await expect(page.getByText("BGM：未设置")).toBeVisible();

  // hear the suggested interlude before deciding
  const change = draft.getByTestId("draft-change").filter({ hasText: "间奏" });
  await change.getByRole("button", { name: "试听" }).click();
  await expect.poll(() => page.getByTestId("placement-audio").evaluate((a: HTMLAudioElement) => a.currentTime)).toBeGreaterThan(0.2);
  await change.getByRole("button", { name: "停止" }).click();
  await draft.getByRole("button", { name: "采用" }).click();
  await expect(page.getByTestId("music-draft")).toHaveCount(0);
  await expect(page.getByTestId("placement")).toHaveCount(2);
  await expect(page.getByTestId("credits")).toContainText("间奏：《奥德赛》原声");

  // one second later, exactly
  const mid = page.getByTestId("placement").filter({ hasText: "间奏" });
  const pos = mid.getByLabel("位置（成品时间）");
  const before = await pos.inputValue();
  const secs = (t: string) => t.split(":").reduce((a, x) => a * 60 + Number(x), 0);
  await mid.getByRole("button", { name: "晚 1 秒" }).click();
  await expect.poll(async () => secs(await pos.inputValue())).toBe(secs(before) + 1);
  await mid.getByRole("button", { name: "早 1 秒" }).click();
  await expect.poll(async () => secs(await pos.inputValue())).toBe(secs(before));

  // talk: quieter interlude → a suggestion → accepted
  const box = page.getByLabel("跟 Claude 说配乐怎么改");
  await box.fill("间奏小 3 dB");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByTestId("music-draft")).toContainText("间奏：音量 -3 dB");
  await expect(mid.getByLabel("音量（dB）")).toHaveValue("0"); // not applied yet
  await page.getByTestId("music-draft").getByRole("button", { name: "采用" }).click();
  await expect(mid.getByLabel("音量（dB）")).toHaveValue("-3");

  // talk about music that isn't there: Claude asks instead of guessing
  await box.fill("片尾去掉");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByTestId("music-msg")).toContainText("现在没有这段配乐");
  await expect(page.getByTestId("music-draft")).toHaveCount(0);

  // talk: a suggestion can be turned down
  await box.fill("间奏晚两秒");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByTestId("music-draft")).toContainText("间奏从");
  await page.getByTestId("music-draft").getByRole("button", { name: "不要" }).click();
  await expect(page.getByTestId("music-draft")).toHaveCount(0);
  await expect.poll(async () => secs(await pos.inputValue())).toBe(secs(before));

  // leave the shared episode and library as they were
  for (const name of ["片头", "间奏"]) {
    await page.getByTestId("placement").filter({ hasText: name }).getByRole("button", { name: "去掉" }).click();
  }
  await expect(page.getByTestId("placement")).toHaveCount(0);
  await page.goto("/#/library");
  await theme.getByLabel("用途").selectOption("other");
  await expect(theme.getByLabel("用途")).toHaveValue("other");
});

// 「带配乐听」: the review player plays the final mix, while the page keeps voice-cut time
test("listen with music in the review player", async ({ page }) => {
  const lib = await (await page.request.get("/api/library")).json();
  const jingle = lib.assets.find((a: { name: string }) => a.name === "洛城片头.wav");
  const m = await (await page.request.post(`/api/episodes/${EP}/music`, { data: { asset_id: jingle.id, role: "intro" } })).json();
  const intro = m.inserts[0][1] as number; // seconds the intro adds before the voice
  expect(m.inserts[0][0]).toBe(0);
  expect(intro).toBeGreaterThan(1);

  await page.goto(`/#/ep/${EP}/listen`);
  const audio = page.getByTestId("main-audio");
  const toggle = page.getByTestId("listen-with-music");
  await expect(toggle).not.toBeChecked();
  await expect(audio).toHaveAttribute("src", /\/audio\//);
  await toggle.check();
  await expect(audio).toHaveAttribute("src", /\/mix\/[0-9a-f]+\.wav$/);
  // voice-cut 0:00 is where the voice comes in on the mix, after the intro
  await expect.poll(() => audio.evaluate((a: HTMLAudioElement) => a.currentTime)).toBeCloseTo(intro, 1);
  await expect(page.getByTestId("clock")).toContainText("0:00 /");
  await expect(page.getByText(/成品 0:0\d/)).toBeVisible();
  // seeking on the page speaks voice-cut time
  await page.getByRole("slider", { name: "播放位置" }).fill("10");
  await expect.poll(() => audio.evaluate((a: HTMLAudioElement) => a.currentTime)).toBeCloseTo(10 + intro, 1);
  await expect(page.getByTestId("clock")).toContainText("0:10 /");
  await toggle.uncheck();
  await expect(audio).toHaveAttribute("src", /\/audio\//);
  await expect.poll(() => audio.evaluate((a: HTMLAudioElement) => a.currentTime)).toBeCloseTo(10, 1);

  // leave the shared episode as it was
  await page.request.delete(`/api/episodes/${EP}/music/${m.placements[0].id}`);
});
