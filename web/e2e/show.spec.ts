import { expect, test } from "@playwright/test";

// 项目设置 (was 节目设置): Leon's project stays 《洛城二三事》 with Leon + Pei; a new project starts generic and asks
// for its show (name + hosts) before the first import.
const PW = "correct horse battery";

test.describe.configure({ mode: "serial" });
test.beforeAll(async ({ request }) => {
  await request.post("/api/auth/_test/reset?skip_setup=false");
});
test.afterAll(async ({ request }) => {
  await request.post("/api/auth/_test/reset?skip_setup=true");
});

test("Leon's workspace keeps his show; a new workspace sets up its own", async ({ browser }) => {
  const leon = await (await browser.newContext()).newPage();
  expect((await leon.request.post("/api/auth/register", { data: { email: "leon@example.com", password: PW } })).ok()).toBeTruthy();
  const inv = await (await leon.request.post("/api/auth/invites", { data: { email: "show@example.com" } })).json();

  // Leon: nothing to set up, his show and hosts as before
  await leon.goto("/#/");
  await expect(leon.getByTestId("show-setup")).toHaveCount(0);
  await expect(leon.getByText("导入 Leon 和 Pei 的分轨")).toBeVisible();
  await leon.getByTestId("project-menu").click();
  await leon.getByTestId("project-settings-link").click();
  await expect(leon.getByTestId("show-name")).toHaveValue("洛城二三事");
  if (process.env.PROJECT_SHOTS) await leon.screenshot({ path: `${process.env.PROJECT_SHOTS}/settings.png`, fullPage: true });
  await leon.getByTestId("project-tab-hosts").click();
  await expect(leon.getByTestId("show-host")).toHaveCount(2);
  await expect(leon.getByLabel("第 1 位主持人的名字")).toHaveValue("Leon");
  await expect(leon.getByLabel("第 2 位主持人的名字")).toHaveValue("Pei");

  // a new account in a workspace of its own: generic, asks for the show first
  const ctx = await browser.newContext();
  const p = await ctx.newPage();
  expect((await p.request.post("/api/auth/register", { data: { invite: inv.link.split("/").at(-1), password: PW } })).ok()).toBeTruthy();
  await p.goto("/");
  const setup = p.getByTestId("show-setup");
  await expect(setup).toBeVisible();
  await expect(setup.getByRole("heading")).toHaveText("建你的第一个节目");
  await expect(p.getByText("导入新一集")).toHaveCount(0);
  await expect(p.locator("body")).not.toContainText("Leon");
  await expect(p.locator("body")).not.toContainText("洛城");
  await setup.getByTestId("show-name").fill("周末电影院");
  await setup.getByLabel("第 1 位主持人的名字").fill("Ana");
  await setup.getByRole("button", { name: "+ 加一位主持人" }).click();
  await setup.getByLabel("第 2 位主持人的名字").fill("Bo");
  await setup.getByRole("button", { name: "+ 加一位主持人" }).click();
  await setup.getByLabel("第 3 位主持人的名字").fill("Cy");
  await setup.getByTestId("show-save").click();
  await expect(setup).toHaveCount(0);
  await expect(p.getByText("导入 Ana、Bo 和 Cy 的分轨")).toBeVisible();
  // the import form asks for one track per host
  await p.getByRole("button", { name: "导入新一集" }).click();
  await expect(p.getByText("把 Ana、Bo 和 Cy 的分轨拖到这里")).toBeVisible();
  for (const n of ["ana", "bo", "cy"]) await expect(p.getByTestId(`import-slot-${n}`)).toBeVisible();
  await expect(p.getByTestId("import-swap")).toHaveCount(0);
  await p.getByRole("button", { name: "取消" }).click();

  // and it is kept, with its own colours
  await expect(p.getByTestId("project-menu")).toHaveText(/周末电影院/);
  await p.getByTestId("project-menu").click();
  await p.getByTestId("project-settings-link").click();
  await expect(p.getByTestId("show-name")).toHaveValue("周末电影院");
  await p.getByTestId("project-tab-hosts").click();
  await p.getByRole("group", { name: "颜色" }).nth(2).getByRole("button", { name: "粉" }).click();
  // a fourth host is the last one: then the page says so instead of offering a fifth
  await p.getByRole("button", { name: "+ 加一位主持人" }).click();
  await p.getByLabel("第 4 位主持人的名字").fill("Dee");
  await expect(p.getByRole("button", { name: "+ 加一位主持人" })).toHaveCount(0);
  await expect(p.getByTestId("show-hosts-max")).toHaveText("每个节目最多 4 位主持人（每人一条分轨）。");
  await p.getByTestId("show-save").click();
  await expect(p.getByText("已保存")).toBeVisible();
  const s = await (await p.request.get("/api/show")).json();
  expect(s.hosts.map((h: { color: string }) => h.color)).toEqual(["blue", "purple", "pink", "teal"]);
  // 专有名词 in 基本信息, one per line
  await p.getByTestId("project-tab-basic").click();
  await p.getByTestId("show-terms").fill("王家卫\n花样年华, PULSE");
  await p.getByTestId("show-save").click();
  await expect(p.getByText("已保存")).toBeVisible();
  expect((await (await p.request.get("/api/show")).json()).terms).toEqual(["王家卫", "花样年华", "PULSE"]);
  await expect(p.getByTestId("show-terms")).toHaveValue("王家卫\n花样年华\nPULSE");

  // Leon's show did not change
  const l = await (await leon.request.get("/api/show")).json();
  expect(l.show_name).toBe("洛城二三事");
  await ctx.close();
});
