import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { SCOPES_PORT } from "../playwright.config";

// Library scopes (整个项目 / 专辑 / 本集) on the fourth server: the default workspace plus a second episode
// (tests/app/e2e/library_scopes.py). Music files are written by tests/app/e2e/library.py.
test.use({ baseURL: `http://127.0.0.1:${SCOPES_PORT}` });

const INBOX = join(dirname(fileURLToPath(import.meta.url)), ".fixtures", "music_inbox");
const EP = "EP_TEST_合成";
const OTHER = "EP_TEST_另一集";

type Asset = { id: string; name: string; shared: boolean; episodes: string[] };

// start from an empty library each time
test.beforeEach(async ({ request }) => {
  for (const a of (await (await request.get("/api/library")).json()).assets as Asset[])
    await request.delete(`/api/library/assets/${a.id}`);
});

test("add into an episode, move / share, and the music page lists only shared + this episode", async ({ page }) => {
  // the theme goes to 公共 (shared), the usual way
  const up = await page.request.post(`/api/library/upload?${new URLSearchParams({ name: "odyssey_theme.mp3", kind: "interlude", note: "" })}`, {
    headers: { "Content-Type": "application/octet-stream" },
    data: readFileSync(join(INBOX, "odyssey_theme.mp3")),
  });
  expect(up.ok()).toBeTruthy();

  await page.goto("/#/library");
  const theme = page.getByTestId("asset-row").filter({ hasText: "odyssey_theme.mp3" });
  await expect(theme.getByTestId("asset-scope")).toHaveText("整个项目");
  await expect(theme.getByRole("button", { name: "设为整个项目" })).toHaveCount(0);

  // the jingle is added straight into this episode (本集)
  await page.getByLabel("新文件加到哪里").selectOption(EP);
  await page.getByLabel("新文件的用途").selectOption("intro");
  // dragged onto the page: the drop zone's choices (use, where it goes) apply
  const bytes = [...readFileSync(join(INBOX, "洛城片头.wav"))];
  const drop = await page.evaluateHandle((b) => {
    const dt = new DataTransfer();
    dt.items.add(new File([new Uint8Array(b)], "洛城片头.wav", { type: "audio/wav" }));
    return dt;
  }, bytes);
  await page.getByTestId("drop-zone").dispatchEvent("dragover", { dataTransfer: drop });
  await page.getByTestId("drop-zone").dispatchEvent("drop", { dataTransfer: drop });
  await expect(page.getByTestId("uploads")).toContainText("已加入：洛城片头.wav");
  const jingle = page.getByTestId("asset-row").filter({ hasText: "洛城片头.wav" });
  await expect(jingle.getByTestId("asset-scope")).toHaveText("本集：合成测试集");
  // credits stay with the asset whatever its scope
  await jingle.getByRole("button", { name: "手动改" }).click();
  await jingle.getByLabel("曲名").fill("洛城二三事 片头");
  await jingle.getByRole("button", { name: "保存署名" }).click();
  await expect(jingle.getByTestId("credit-line")).toContainText("“洛城二三事 片头”");

  // filter: 公共 / one episode
  await page.getByLabel("按范围筛选").selectOption("shared");
  await expect(page.getByTestId("asset-row")).toHaveCount(1);
  await expect(theme).toHaveCount(1);
  await page.getByLabel("按范围筛选").selectOption(`ep:${EP}`);
  await expect(page.getByTestId("asset-row")).toHaveCount(1);
  await expect(jingle).toHaveCount(1);
  await page.getByLabel("按范围筛选").selectOption("");
  await expect(page.getByTestId("asset-row")).toHaveCount(2);

  // the theme moves to the other episode: no longer shared
  await theme.getByLabel("挪到某一集").selectOption(OTHER);
  await expect(theme.getByTestId("asset-scope")).toHaveText("本集：另一集（范围测试）");
  await expect(theme.getByRole("button", { name: "设为整个项目" })).toBeVisible();

  // ---- this episode's music page: its own jingle, not the other episode's theme
  await page.goto(`/#/ep/${encodeURIComponent(EP)}/music`);
  await expect(page.getByRole("heading", { name: "配乐", exact: true })).toBeVisible();
  const picker = page.getByLabel("选择素材").locator("option");
  await expect(picker).toHaveCount(1);
  await expect(picker.first()).toContainText("洛城片头.wav");

  // uploading on the music page puts the file into this episode (the theme now in both)
  await page.getByTestId("episode-upload").getByLabel("选择音乐文件").setInputFiles(join(INBOX, "odyssey_theme.mp3"));
  await expect(page.getByText("已加到这一集：odyssey_theme.mp3")).toBeVisible();
  await expect(picker).toHaveCount(2);
  const lib = (await (await page.request.get("/api/library")).json()).assets as Asset[];
  expect(lib.find((a) => a.name === "odyssey_theme.mp3")?.episodes).toEqual([OTHER, EP]);

  // the other episode's page offers only the theme (the jingle is this episode's alone)
  await page.goto(`/#/ep/${encodeURIComponent(OTHER)}/music`);
  await expect(page.getByRole("heading", { name: "配乐", exact: true })).toBeVisible();
  await expect(picker).toHaveCount(1);
  await expect(picker.first()).toContainText("odyssey_theme.mp3");

  // made shared in the library: now every episode offers the jingle
  await page.goto("/#/library");
  await jingle.getByRole("button", { name: "设为整个项目" }).click();
  await expect(jingle.getByTestId("asset-scope")).toHaveText("整个项目");
  await expect(jingle.getByTestId("credit-line")).toContainText("“洛城二三事 片头”");
  await page.goto(`/#/ep/${encodeURIComponent(OTHER)}/music`);
  await expect(picker).toHaveCount(2);
});
