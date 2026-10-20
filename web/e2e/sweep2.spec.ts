import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { SCOPES_PORT } from "../playwright.config";

// Second full scan (2026-10-18): the music page where library scopes (V10) meet adding music.
test.use({ baseURL: `http://127.0.0.1:${SCOPES_PORT}` });

const INBOX = join(dirname(fileURLToPath(import.meta.url)), ".fixtures", "music_inbox");
const EP = "EP_TEST_合成";
const OTHER = "EP_TEST_另一集";

test.beforeEach(async ({ request }) => {
  for (const a of (await (await request.get("/api/library")).json()).assets as { id: string }[])
    await request.delete(`/api/library/assets/${a.id}`);
});

// as a buffer: a non-ASCII *path* given to setInputFiles never reaches the page on a POSIX-locale box
const file = (name: string) => ({ name, mimeType: name.endsWith(".wav") ? "audio/wav" : "audio/mpeg", buffer: readFileSync(join(INBOX, name)) });

async function upload(page: import("@playwright/test").Page, file: string, kind: string, episode = "") {
  const q = new URLSearchParams({ name: file, kind, note: "" });
  if (episode) q.set("episode", episode);
  const r = await page.request.post(`/api/library/upload?${q}`, {
    headers: { "Content-Type": "application/octet-stream" },
    data: readFileSync(join(INBOX, file)),
  });
  expect(r.ok()).toBeTruthy();
}

test("music page: only another episode's files → says how to get one; a file added here is picked", async ({ page }) => {
  await upload(page, "odyssey_theme.mp3", "interlude", OTHER);
  await page.goto(`/#/ep/${encodeURIComponent(EP)}/music`);
  await expect(page.getByRole("heading", { name: "配乐", exact: true })).toBeVisible();
  // the library isn't empty, this episode just can't use what is in it
  await expect(page.getByTestId("music-no-assets")).toContainText("这一集还没有能用的素材");
  await expect(page.getByTestId("music-no-assets")).not.toContainText("素材库里还没有音乐");

  // added here: it belongs to this episode and is the one picked, ready to 放进去
  await page.getByTestId("episode-upload").getByLabel("上传的文件当作").selectOption("intro");
  await page.getByTestId("episode-upload").getByLabel("选择音乐文件").setInputFiles(file("洛城片头.wav"));
  await expect(page.getByText("已加到这一集：洛城片头.wav")).toBeVisible();
  const picker = page.getByLabel("选择素材");
  await expect(picker.locator("option:checked")).toContainText("洛城片头.wav");
  await expect(page.getByLabel("用途", { exact: true })).toHaveValue("intro");

  // a second file added here becomes the picked one too
  await page.getByTestId("episode-upload").getByLabel("上传的文件当作").selectOption("interlude");
  await page.getByTestId("episode-upload").getByLabel("选择音乐文件").setInputFiles(file("odyssey_theme.mp3"));
  await expect(picker.locator("option")).toHaveCount(2);
  await expect(picker.locator("option:checked")).toContainText("odyssey_theme.mp3");
});

test("music page: adding a file the library already has as shared says so", async ({ page }) => {
  await upload(page, "odyssey_theme.mp3", "interlude");
  await page.goto(`/#/ep/${encodeURIComponent(EP)}/music`);
  await expect(page.getByRole("heading", { name: "配乐", exact: true })).toBeVisible();
  await page.getByTestId("episode-upload").getByLabel("选择音乐文件").setInputFiles(file("odyssey_theme.mp3"));
  await expect(page.getByText("素材库里已经有这首（整个项目都能用），这一集直接能用：odyssey_theme.mp3")).toBeVisible();
  const lib = (await (await page.request.get("/api/library")).json()).assets as { shared: boolean }[];
  expect(lib).toHaveLength(1);
  expect(lib[0].shared).toBe(true);
});
