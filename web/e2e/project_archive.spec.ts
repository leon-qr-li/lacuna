import { expect, test } from "@playwright/test";

// project picture / colour, archive and deleting for good (decision projects-archive-delete), on the
// default server: Leon starts a project, gives it a picture, archives it (read-only, under 已归档) and
// deletes it for good by typing its name.
const PW = "correct horse battery";
// a 2×1 red PNG: the server cuts it to a square
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAIAAAABCAIAAAB7QOjdAAAAEElEQVR4nGP4z8DAwMDAAAAWAAEB3RMmPQAAAABJRU5ErkJggg==", "base64");

test.describe.configure({ mode: "serial" });
test.beforeAll(async ({ request }) => {
  await request.post("/api/auth/_test/reset?skip_setup=false");
});
test.afterAll(async ({ request }) => {
  await request.post("/api/auth/_test/reset?skip_setup=true");
});

test("a project gets a colour, a picture, is archived read-only, then deleted for good", async ({ page }) => {
  expect((await page.request.post("/api/auth/register", { data: { email: "leon@example.com", password: PW } })).ok()).toBeTruthy();
  await page.goto("/");
  await expect(page.getByTestId("project-menu")).toBeVisible();
  // a new project has its own solid colour, different from Leon's main project
  const before = await (await page.request.get("/api/spaces")).json();
  const made = await (await page.request.post("/api/spaces", { data: { name: "旧节目" } })).json();
  const row = made.mine.find((m: { id: string }) => m.id === made.created);
  expect(row.color).not.toBe(before.current.color);
  expect(row.picture).toBeNull();

  await page.goto("/#/project/basic");
  await page.reload(); // the page loaded before the project was made
  // the reload re-opens the whole app (sign-in check, projects, show): slow on macOS CI
  await expect(page.getByTestId("project-menu")).toHaveText(/旧节目/, { timeout: 20_000 });
  await expect(page.getByTestId("project-look").getByTestId("project-color")).toHaveText("旧");
  await page.getByTestId("project-picture-file").setInputFiles({ name: "p.png", mimeType: "image/png", buffer: PNG });
  await expect(page.getByTestId("project-look").getByTestId("project-picture")).toBeVisible();
  await expect(page.getByTestId("project-menu").getByTestId("project-picture")).toBeVisible();
  await page.getByTestId("project-picture-remove").click();
  await expect(page.getByTestId("project-look").getByTestId("project-color")).toBeVisible();

  // archive: confirm in the app's own dialog; the project becomes read-only for everyone
  await page.getByTestId("project-archive-btn").click();
  await page.getByTestId("dialog").getByRole("button", { name: "归档", exact: true }).click();
  await expect(page.getByTestId("project-readonly")).toBeVisible();
  await expect(page.getByTestId("project-archived-tag")).toHaveText("已归档 · 只读");
  const r = await page.request.put("/api/show", { data: { name: "改名" } });
  expect(r.status()).toBe(403);
  expect((await r.json()).detail).toContain("已归档");

  // 所有项目: it sits under 已归档; deleting asks for its name typed exactly
  await page.goto("/#/projects");
  const archive = page.getByTestId("project-archive");
  await expect(archive.getByTestId("project-card")).toContainText("旧节目");
  await expect(page.getByTestId("project-list").getByTestId("project-card").filter({ hasText: "旧节目" })).toHaveCount(0);
  await archive.getByTestId("project-delete").click();
  const dlg = page.getByTestId("project-delete-dialog");
  await expect(dlg).toContainText("永久删除「旧节目」");
  await dlg.getByTestId("project-delete-name").fill("旧节");
  await expect(dlg.getByTestId("project-delete-confirm")).toBeDisabled();
  await dlg.getByTestId("project-delete-name").fill("旧节目");
  await dlg.getByTestId("project-delete-confirm").click();
  await expect(dlg).toHaveCount(0);
  await expect(page.getByTestId("project-archive")).toHaveCount(0);
  const after = await (await page.request.get("/api/spaces")).json();
  expect(after.mine.map((m: { name: string }) => m.name)).not.toContain("旧节目");

  // restoring: archive Leon's main project from the API, restore it from 所有项目
  await page.request.post("/api/spaces/main/archive", { data: { archived: true } });
  await page.reload();
  await page.getByTestId("project-archive").getByTestId("project-restore").click();
  await expect(page.getByTestId("project-archive")).toHaveCount(0);
  expect((await (await page.request.get("/api/spaces")).json()).mine[0].archived).toBe(false);
});

test("节目设置 is on the show's home; archive then delete for good right there (Leon 2026-10-24)", async ({ page }) => {
  await page.request.post("/api/auth/login", { data: { email: "leon@example.com", password: PW } });
  // one show: 所有节目 is still in the menu
  expect((await (await page.request.get("/api/spaces")).json()).mine).toHaveLength(1);
  await page.goto("/#/");
  await page.getByTestId("project-menu").click();
  await expect(page.getByTestId("project-all-link")).toBeVisible();
  await page.keyboard.press("Escape");

  const made = await (await page.request.post("/api/spaces", { data: { name: "试播" } })).json();
  expect(made.current.id).toBe(made.created); // moved into it
  // set up (a new show's 首页 is the 建节目 form until then)
  const before = await (await page.request.get("/api/show")).json();
  expect((await page.request.put("/api/show", { data: { ...before, show_name: "试播", hosts: [{ name: "Leon" }] } })).ok()).toBeTruthy();
  await page.goto("/#/");
  await page.reload();
  await expect(page.getByTestId("project-menu")).toHaveText(/试播/, { timeout: 20_000 });
  await page.getByTestId("home-project-settings").click();
  await expect(page).toHaveURL(/#\/project$/);
  await page.getByTestId("project-archive-btn").click();
  await page.getByTestId("dialog").getByRole("button", { name: "归档", exact: true }).click();
  await page.getByTestId("project-readonly").getByTestId("project-settings-delete").click();
  const dlg = page.getByTestId("project-delete-dialog");
  await expect(dlg).toContainText("不能恢复");   // the 60 days are for LACUNA staff only
  await dlg.getByTestId("project-delete-name").fill("试播");
  await dlg.getByTestId("project-delete-confirm").click();
  await expect.poll(async () => (await (await page.request.get("/api/spaces")).json()).mine.map((m: { name: string }) => m.name)).not.toContain("试播");
  await expect(page.locator("h1.home-title")).toBeVisible({ timeout: 20_000 });
  // kept 60 days: the site owner brings it back from the 回收区 (设置 → 成员与邀请)
  await page.goto("/#/settings/members");
  const trash = page.getByTestId("trash-card");
  const item = trash.getByTestId("trash-item").filter({ hasText: "试播" });
  await expect(item).toContainText("还剩 59 天");
  await item.getByTestId("trash-restore").click();
  await page.getByTestId("dialog").getByRole("button", { name: "恢复", exact: true }).click();
  await expect(item).toHaveCount(0);
  const back = (await (await page.request.get("/api/spaces")).json()).mine.find((m: { name: string }) => m.name === "试播");
  expect(back.archived).toBeTruthy();
});
