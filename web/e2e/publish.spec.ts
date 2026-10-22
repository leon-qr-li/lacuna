import { expect, test } from "@playwright/test";

// AI workspace; the publish pack is written by a scripted fake Claude (tests/app/fake_claude.py)
test.use({ baseURL: "http://127.0.0.1:8798" });

test("publish pack: generate → show notes → copy → title / name / edit → stale after a cut change → retime", async ({
  page,
  context,
}) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto("/");
  await expect(page).toHaveURL(/#\/ep\/.+\/listen/, { timeout: 20_000 });
  await page.getByRole("link", { name: "发布", exact: true }).click(); // 发布 step opens its first sub-tab
  await expect(page.getByRole("link", { name: "发布资料", exact: true })).toHaveAttribute("aria-current", "page");
  await expect(page).toHaveURL(/\/publish$/);
  await expect(page.getByRole("heading", { name: "发布资料" })).toBeVisible();

  await page.getByRole("button", { name: "生成发布资料" }).click();
  await expect(page.getByTestId("publish-running")).toBeVisible();
  await expect(page.getByTestId("publish-title")).toHaveText("合成的一期：两部电影", { timeout: 15_000 });
  const notes = page.getByTestId("show-notes");
  await expect(notes.getByRole("heading", { name: "合成的一期：两部电影" })).toBeVisible();
  await expect(notes.getByRole("heading", { name: "⏱ 时间轴" })).toBeVisible();
  await expect(notes.getByRole("heading", { name: "暖场" })).toBeVisible();
  await expect(notes.getByRole("listitem").filter({ hasText: "《一部电影》：结尾" })).toBeVisible(); // no tables (item 26)
  await expect(notes.locator("table")).toHaveCount(0);
  await expect(notes.getByRole("heading", { name: "🎵 本期 BGM" })).toBeVisible();
  await expect(notes.locator("h3 + ul li strong").first()).toHaveText(/^\d\d:\d\d$/);
  await expect(page.getByRole("region", { name: "章节" })).toContainText("暖场");

  // copy: rich text + Markdown source together
  await page.getByRole("button", { name: "复制（带格式）" }).click();
  await expect(page.getByRole("status")).toContainText("已复制");
  const clip = await page.evaluate(async () => {
    const items = await navigator.clipboard.read();
    const html = await (await items[0].getType("text/html")).text();
    const text = await (await items[0].getType("text/plain")).text();
    return { html, text };
  });
  expect(clip.text.startsWith("# 合成的一期：两部电影")).toBe(true);
  expect(clip.html).toContain("<h1>合成的一期：两部电影</h1>");
  expect(clip.html).not.toContain("<table");
  expect(clip.text).not.toContain("|");

  // switch to an alternative title
  await page.getByRole("button", { name: "两部电影一个结尾" }).click();
  await expect(page.getByTestId("publish-title")).toHaveText("两部电影一个结尾");
  await expect(notes.getByRole("heading", { name: "两部电影一个结尾" })).toBeVisible();

  // a misheard name: fix everywhere
  const name = page.getByTestId("name-check");
  await expect(name).toContainText("听成「结尾」");
  await name.getByRole("button", { name: "改成「结局」" }).click();
  await expect(name).toContainText("已改");
  await expect(page.getByTestId("publish-title")).toHaveText("两部电影一个结局");

  // someone else saves while this page still shows the older version (co-editing, features/coedit):
  // the save is refused, the latest shows, and what was typed stays below it to copy from
  const pub = `/api/episodes/${encodeURIComponent(decodeURIComponent(/#\/ep\/([^/]+)/.exec(page.url())![1]))}/publish`;
  await page.getByRole("button", { name: "编辑" }).click();
  await page.getByRole("textbox", { name: "Markdown" }).fill("# 我这边写的\n");
  const rev = (await (await page.request.get(pub)).json()).pack.rev;
  expect((await page.request.put(pub, { data: { title: "另一位成员换的标题", rev } })).ok()).toBe(true);
  await page.getByRole("button", { name: "保存" }).click();
  const dlg = page.getByRole("alertdialog");
  await expect(dlg).toContainText("刚刚修改了发布资料");
  await dlg.getByRole("button").first().click();
  await expect(page.getByTestId("publish-mine").getByRole("textbox")).toHaveValue("# 我这边写的\n");
  await expect(page.getByRole("textbox", { name: "Markdown" })).toHaveValue(/# 另一位成员换的标题/);
  await page.getByRole("button", { name: "取消" }).click();
  await expect(page.getByTestId("publish-title")).toHaveText("另一位成员换的标题");
  await expect(notes).not.toContainText("我这边写的");

  // hand edit, saved, survives reload
  await page.getByRole("button", { name: "编辑" }).click();
  const box = page.getByRole("textbox", { name: "Markdown" });
  await box.fill((await box.inputValue()).replace("一个月没见", "好久不见"));
  await page.getByRole("button", { name: "保存" }).click();
  await expect(notes).toContainText("好久不见");
  await page.reload();
  await expect(page.getByTestId("show-notes")).toContainText("好久不见");
  await expect(page.getByText("Show notes · 已手改")).toBeVisible();

  // change the cut → timestamps are stale → update them locally, wording kept
  const ep = decodeURIComponent(/#\/ep\/([^/]+)/.exec(page.url())![1]);
  const summary = await (await page.request.get(`/api/episodes/${encodeURIComponent(ep)}`)).json();
  const first = summary.edits.find((e: { status: string; len: number; t: number }) => e.status === "applied" && e.len > 0.3 && e.t < 5);
  const r = await page.request.post(`/api/episodes/${encodeURIComponent(ep)}/edits/${first.id}/review`, {
    data: { action: "restore" },
  });
  expect(r.ok()).toBe(true);
  await page.reload();
  await expect(page.getByTestId("publish-stale")).toBeVisible();
  await page.getByRole("button", { name: "更新时间戳" }).click();
  await expect(page.getByTestId("publish-stale")).toBeHidden();
  await expect(page.getByTestId("show-notes")).toContainText("好久不见");
});
