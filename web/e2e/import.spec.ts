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
  await expect(page.getByText("工作区里还没有剧集")).toBeVisible();
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
  await expect(page.getByTestId("import-stage")).toContainText("AI 第一刀");
  await expect(page.getByTestId("import-stage")).toContainText("每段约 10 分钟录音");
  await expect(page.getByTestId("import-progress-left")).toBeVisible();      // the server's estimate
  await expect(page.getByRole("button", { name: "导入新一集" })).toBeDisabled(); // one import at a time

  // done → the app opens the review by itself
  await expect(page).toHaveURL(/#\/ep\/EP001\/review$/, { timeout: 30_000 });
  await expect(page.locator(".ep-title")).toHaveText("EP001 · 导入测试");
  const items = page.getByTestId("review-list").locator(".ritem");
  await expect(items).toHaveCount(2);
  // timeline order: the earlier filler comes first, the content trim after it
  await expect(items.nth(1)).toHaveAttribute("data-category", "content");
  await items.nth(1).click();
  await expect(page.getByText("这段题外话和主线无关，后面没有再提")).toBeVisible();

  // back home (no auto-redirect): the task shows as done with a link to the review
  await page.locator("a.brand").click();
  await expect(page.getByTestId("import-job")).toHaveAttribute("data-state", "done");
  await expect(page.getByTestId("import-job")).toContainText("2 处需要你过目");
  await expect(page.locator(".ep-list")).toContainText("EP001 · 导入测试");
  await page.getByRole("link", { name: "开始审阅" }).click();
  await expect(page).toHaveURL(/#\/ep\/EP001\/review$/);
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
  await expect(page.getByText("没有归档的剧集。")).toBeVisible();
  expect((await page.request.get("/api/episodes/EP001")).status()).toBe(404);
  // the id is free again: the next import suggests EP001 and starts from scratch
  await page.goto("/#/");
  await expect(page.getByText("工作区里还没有剧集")).toBeVisible();
});
