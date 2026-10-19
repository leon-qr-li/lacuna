import { expect, test } from "@playwright/test";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

// 设置 → 从电脑搬过来 is cloud-only (the server side: tests/app/test_migrate.py); here the shared
// server is the desktop one, so the cloud answers are faked and the browser part is tested for real.
test("设置: move the desktop workspace, resuming and skipping server-only folders", async ({ page }) => {
  const root = join(mkdtempSync(join(tmpdir(), "lacuna-mig-")), "LACUNA_Workspace");
  for (const [rel, body] of [
    ["episodes/EP1/state.json", "{}"],
    ["library/a.mp3", "abc"],
    ["models/m.onnx", "model"],
    ["auth/users.json", "{}"],
  ]) {
    mkdirSync(join(root, rel, ".."), { recursive: true });
    writeFileSync(join(root, rel), body);
  }
  const sent: string[] = [];
  let finished: unknown = null;
  await page.route("**/api/app", async (route) => {
    const res = await route.fetch();
    await route.fulfill({ response: res, json: { ...(await res.json()), cloud: true } });
  });
  // library/a.mp3 already arrived in an earlier try
  await page.route("**/api/migrate", (r) => r.fulfill({ json: { staged: { "library/a.mp3": 3 }, episodes: 0 } }));
  await page.route("**/api/migrate/file?*", (r) => {
    sent.push(new URL(r.request().url()).searchParams.get("path")!);
    return r.fulfill({ json: { size: r.request().postDataBuffer()?.length ?? 0 } });
  });
  await page.route("**/api/migrate/finish", (r) => {
    finished = r.request().postDataJSON();
    return r.fulfill({ json: { files: 2, bytes: 5, episodes: 1, rewritten: 1, restarting: true } });
  });

  await page.goto("/#/settings");
  const card = page.getByTestId("migrate-card");
  await expect(card).toContainText("从电脑搬过来");
  await expect(card).toContainText("上次已经传了 1 个文件");
  await page.getByTestId("migrate-input").setInputFiles(root);
  await expect(page.getByTestId("migrate-picked")).toHaveText("选好了：2 个文件，共 1 MB。");
  await page.getByTestId("migrate-start").click();
  await expect(page.getByTestId("migrate-done")).toContainText("搬好了：1 集，2 个文件", { timeout: 15_000 });
  expect(sent).toEqual(["episodes/EP1/state.json"]);       // resumed: the library file was not sent again
  expect(finished).toEqual({ files: 2, bytes: 5 });
});

test("设置: the move card stays hidden on the desktop", async ({ page }) => {
  await page.goto("/#/settings");
  await expect(page.getByRole("heading", { name: "设置" })).toBeVisible();
  await expect(page.getByTestId("migrate-card")).toHaveCount(0);
});
