import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test, type Locator, type Page } from "@playwright/test";
import { scan } from "./contrast-scan";

// served by the third webServer in playwright.config.ts: empty workspace, fake ASR + fake Claude
// first cut (the rest - decoding, features, op conversion, episode - is real). The tracks are the
// synthetic Leon.wav / Pei.wav (tests/app/synth.py), written here so the browser can drop them.
test.use({ baseURL: "http://127.0.0.1:8797" });
test.describe.configure({ mode: "serial" });

const PYTHON = process.env.PYTHON ?? (process.platform === "win32" ? "python" : "python3");
const REC = mkdtempSync(join(tmpdir(), "lacuna-rec-"));
execFileSync(PYTHON, ["-c", "import sys; from tests.app.synth import write_recordings; write_recordings(sys.argv[1])", REC], {
  cwd: fileURLToPath(new URL("../..", import.meta.url)),
});
const LEON = join(REC, "Leon.wav");
const PEI = join(REC, "Pei.wav");

/** Drop files on `target` the way a browser does when they are dragged in from the desktop. */
async function dropFiles(page: Page, target: Locator, files: string[]) {
  const data = files.map((f) => ({ name: f.split(/[\\/]/).pop()!, b64: readFileSync(f).toString("base64") }));
  const dt = await page.evaluateHandle((fs) => {
    const t = new DataTransfer();
    for (const f of fs) {
      const bin = atob(f.b64);
      const bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      t.items.add(new File([bytes], f.name, { type: "audio/wav" }));
    }
    return t;
  }, data);
  await target.dispatchEvent("dragenter", { dataTransfer: dt });
  await target.dispatchEvent("dragover", { dataTransfer: dt });
  await target.dispatchEvent("drop", { dataTransfer: dt });
}

test("import: drag both tracks in → progress with time left → straight into review", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("这个节目里还没有剧集")).toBeVisible();
  await page.getByRole("button", { name: "导入新一集" }).click();
  await expect(page.getByTestId("import-id")).toHaveValue("EP001");
  await page.getByTestId("import-title").fill("EP001 · 导入测试");
  // no folder browser any more: a drop zone like the media library's, with a 选择文件 button
  const zone = page.getByTestId("import-drop");
  await expect(zone).toContainText("把 Leon 和 Pei 的分轨拖到这里");
  await expect(zone.getByRole("button", { name: "选择文件" })).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);

  // dropped in the "wrong" order: the names say whose track is whose
  await dropFiles(page, zone, [PEI, LEON]);
  await expect(page.getByTestId("import-leon")).toHaveText("Leon.wav");
  await expect(page.getByTestId("import-pei")).toHaveText("Pei.wav");
  await expect(page.getByTestId("import-slot-leon")).toContainText("1:00");
  // swap and swap back
  await page.getByTestId("import-swap").click();
  await expect(page.getByTestId("import-leon")).toHaveText("Pei.wav");
  await page.getByTestId("import-swap").click();
  await expect(page.getByTestId("import-leon")).toHaveText("Leon.wav");
  // one slot replaced through the system file dialog (Pei's slot gets Pei.wav again)
  await page.getByTestId("import-file-pei").setInputFiles(PEI);
  await expect(page.getByTestId("import-pei")).toHaveText("Pei.wav");
  for (const theme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme: theme });      // the app follows the system theme
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    await page.waitForTimeout(500);                         // colors ease over on a theme switch
    expect((await scan(page)).bad).toEqual([]);
    if (process.env.IMPORT_SHOTS) await page.screenshot({ path: `${process.env.IMPORT_SHOTS}/import_form_${theme}.png` });
  }
  await page.emulateMedia({ colorScheme: "light" });

  await page.getByRole("button", { name: "开始导入" }).click();
  const job = page.getByTestId("import-job");
  await expect(job).toHaveAttribute("data-state", /queued|running/);
  await expect(job.getByRole("progressbar")).toBeVisible();
  await expect(page.getByTestId("import-stage")).toContainText("LACUNA 初剪");
  await expect(page.getByTestId("import-stage")).toContainText("每段约 10 分钟录音");
  await expect(page.getByTestId("import-progress-left")).toBeVisible();      // the server's estimate
  await expect(page.getByRole("button", { name: "导入新一集" })).toBeEnabled(); // another one would wait its turn

  // done → the app opens the review by itself
  await expect(page).toHaveURL(/#\/ep\/EP001\/review$/, { timeout: 30_000 });
  await expect(page.locator(".ep-title")).toHaveText("EP001 · 导入测试");
  const items = page.getByTestId("review-list").locator(".ritem");
  await expect(items).toHaveCount(2);
  // timeline order: the earlier filler comes first, the content trim after it
  await expect(items.nth(1)).toHaveAttribute("data-category", "content");
  await items.nth(1).click();
  await expect(page.getByText("这段题外话和主线无关，后面没有再提")).toBeVisible();

  // back home (no auto-redirect): the episode card says what is left; the finished task card is gone (H8)
  await page.locator("a.brand").click();
  await expect(page.locator(".ep-list")).toContainText("EP001 · 导入测试");
  await expect(page.locator(".ep-list")).toContainText("2 处待审阅");
  await expect(page.getByTestId("import-job")).toHaveCount(0);
  await page.locator(".ep-list a").filter({ hasText: "EP001" }).first().click();
  await page.getByRole("link", { name: /审阅改动/ }).click();
  await expect(page).toHaveURL(/#\/ep\/EP001\/review$/);

  // the card follows the review: once everything is looked at, it says so
  await items.first().click();
  await page.keyboard.press("k");
  await expect(page.getByTestId("review-progress")).toContainText("已看 1 / 2");
  await items.nth(1).click();
  await page.keyboard.press("k");
  await expect(page.getByTestId("review-progress")).toContainText("已看 2 / 2");
  await page.locator("a.brand").click();
  await expect(page.locator(".ep-list")).toContainText("都审阅完了");
  await expect(page.getByRole("heading", { name: "导入任务" })).toHaveCount(0);
});

test("import: a file dropped anywhere on 剧集 opens the form; a slot takes a drop of its own", async ({ page }) => {
  await page.goto("/#/");
  await dropFiles(page, page.locator("main.home"), [LEON]);
  await expect(page.getByTestId("import-leon")).toHaveText("Leon.wav");
  await expect(page.getByTestId("import-pei")).toHaveText("还没选");
  await dropFiles(page, page.getByTestId("import-slot-pei"), [LEON]);   // an unhelpful name: still Pei's slot
  await expect(page.getByTestId("import-pei")).toHaveText("Leon.wav");
  await page.getByRole("button", { name: "取消" }).click();
  await expect(page.getByTestId("import-drop")).toHaveCount(0);
});

test("import: tracks keep uploading on another page; the top bar shows them; the form comes back as it was", async ({ page }) => {
  // hold the server's answer, so the track is still "uploading" while we look elsewhere
  let release!: () => void;
  const held = new Promise<void>((r) => (release = r));
  await page.route("**/api/imports/tracks?*", async (route) => {
    await held;
    await route.continue();
  });
  await page.goto("/#/");
  await page.getByRole("button", { name: "导入新一集" }).click();
  await page.getByTestId("import-title").fill("还在传");
  await page.getByTestId("import-file-leon").setInputFiles(LEON);
  await expect(page.getByTestId("import-leon")).toContainText("正在读入 Leon.wav");
  await expect(page.getByTestId("upload-badge")).toHaveCount(0); // the form is on screen: no badge
  await page.goto("/#/settings");
  const badge = page.getByTestId("upload-badge");
  await expect(badge).toContainText(/正在上传 EP\d+ · \d+%/);
  await badge.click();
  await expect(page).toHaveURL(/#\/$/);
  release();
  await expect(page.getByTestId("import-title")).toHaveValue("还在传");
  await expect(page.getByTestId("import-leon")).toHaveText("Leon.wav"); // finished while we were away
  await expect(page.getByTestId("upload-badge")).toHaveCount(0);
  await page.getByTestId("import-cancel").click();
  await expect(page.getByTestId("import-drop")).toHaveCount(0);
  await page.unroute("**/api/imports/tracks?*");
});

test("archive the imported episode, then delete it for good", async ({ page }) => {
  await page.goto("/#/");
  const card = page.getByTestId("episode").filter({ hasText: "EP001 · 导入测试" });
  await card.getByRole("button", { name: "归档「EP001 · 导入测试」" }).click();
  await expect(card).toHaveCount(0);
  await page.getByTestId("archived-link").click();
  await expect(page).toHaveURL(/#\/archive$/);
  const row = page.getByTestId("episode").filter({ hasText: "EP001 · 导入测试" });
  await row.getByRole("button", { name: "永久删除" }).click();
  const dlg = page.getByRole("alertdialog");
  await expect(dlg).toContainText("学到的习惯和规则都会保留");
  await dlg.getByRole("button", { name: "取消" }).click();
  await expect(dlg).toHaveCount(0);
  await expect(row).toHaveCount(1);
  await row.getByRole("button", { name: "永久删除" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "永久删除" }).click();
  await expect(page.getByRole("status").filter({ hasText: "已永久删除" })).toContainText("学到的习惯都还在");
  await expect(page.getByTestId("archive-empty")).toBeVisible();
  expect((await page.request.get("/api/episodes/EP001")).status()).toBe(404);
  // the id is free again: the next import suggests EP001 and starts from scratch
  await page.goto("/#/");
  await expect(page.getByText("这个节目里还没有剧集")).toBeVisible();
});

test("import: a show whose hosts aren't Leon + Pei (a new project) lists its tracks on the task card", async ({ page }) => {
  // a new project's hosts get tags other than L / P; the task card used to read tracks.L and went blank
  const before = await (await page.request.get("/api/show")).json();
  const put = (hosts: { name: string }[]) => page.request.put("/api/show", { data: { ...before, hosts } });
  expect((await put([{ name: "Ann" }, { name: "Bo" }])).ok()).toBeTruthy();
  try {
    await page.goto("/#/");
    await page.getByRole("button", { name: "导入新一集" }).click();
    await page.getByTestId("import-file-ann").setInputFiles(LEON);
    await page.getByTestId("import-file-bo").setInputFiles(PEI);
    await expect(page.getByTestId("import-bo")).toHaveText("Pei.wav");
    await page.getByRole("button", { name: "开始导入" }).click();
    const job = page.getByTestId("import-job");
    await expect(job).toContainText("Leon.wav + Pei.wav · 1:00");
    await expect(page.locator("a.brand")).toBeVisible(); // the page still renders
    await expect(page).toHaveURL(/#\/ep\/EP\d+\/review$/, { timeout: 30_000 }); // and the import finishes
  } finally {
    await put(before.hosts);
  }
});
