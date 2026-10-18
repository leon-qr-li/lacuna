import { expect, test } from "@playwright/test";

// 「喜马拉雅版」 (backlog item 26): AI workspace, publish pack written by the scripted fake Claude
test.use({ baseURL: "http://127.0.0.1:8798" });

const TIME = /^\d{1,2}:\d{2}(:\d{2})?\s/;

test("ximalaya layout: three styles, timestamps first on their lines, copy rich + plain, images for 图文", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto("/");
  await expect(page).toHaveURL(/#\/ep\/.+\/listen/);
  const ep = /#\/ep\/([^/]+)/.exec(page.url())![1];

  // without a publish pack the tab points to 发布资料 (unless an earlier test made one)
  await page.goto(`/#/ep/${ep}/publish`);
  await expect(page.getByRole("heading", { name: "发布资料" })).toBeVisible();
  const gen = page.getByRole("button", { name: "生成发布资料" });
  if (await gen.isVisible()) {
    await page.goto(`/#/ep/${ep}/ximalaya`);
    await expect(page.getByText("还没有发布资料。先去")).toBeVisible();
    await page.goto(`/#/ep/${ep}/publish`);
    await gen.click();
    await expect(page.getByTestId("publish-title")).toBeVisible({ timeout: 15_000 });
  }

  await page.getByRole("link", { name: "喜马拉雅版", exact: true }).click();
  await expect(page).toHaveURL(/\/ximalaya$/);
  await expect(page.getByRole("heading", { name: "喜马拉雅版" })).toBeVisible();
  const styles = page.getByRole("radiogroup", { name: "排版样式" }).getByRole("radio");
  await expect(styles).toHaveCount(3);
  await expect(styles.nth(0)).toContainText("杂志");
  await expect(styles.nth(1)).toContainText("片场");
  await expect(styles.nth(2)).toContainText("图文");

  const preview = page.getByTestId("xmly-preview");
  for (const s of ["magazine", "cinema", "cards"]) {
    await page.getByTestId(`xmly-style-${s}`).click();
    await expect(page.getByTestId(`xmly-style-${s}`)).toHaveAttribute("aria-checked", "true");
    await expect(preview.locator("table, ul, ol")).toHaveCount(0);
    const times = await preview.locator("p").allInnerTexts();
    expect(times.filter((x) => TIME.test(x)).length).toBeGreaterThanOrEqual(5);

    await page.evaluate(() => navigator.clipboard.writeText(""));
    await page.getByTestId("xmly-copy").click();
    await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).not.toBe("");
    await expect(page.getByRole("status")).toContainText("已复制");
    const clip = await page.evaluate(async () => {
      const items = await navigator.clipboard.read();
      return {
        html: await (await items[0].getType("text/html")).text(),
        text: (await (await items[0].getType("text/plain")).text()).replace(/\r\n/g, "\n"), // Windows clipboard
      };
    });
    expect(clip.html).not.toMatch(/<table|<ul|<li|<img/);
    const lines = clip.text.trim().split("\n\n");
    expect(lines.every((l) => !l.includes("\n"))).toBe(true); // blank line between every line
    expect(lines.filter((l) => TIME.test(l)).length).toBeGreaterThanOrEqual(5);
    expect(clip.text).toContain("《一部电影》");
    if (s === "cards") expect(clip.text).toContain("【插图：在这一行插入图片 banner.png");
  }

  // 图文: the two designed images are shown in the preview and offered for download
  const images = page.getByRole("region", { name: "配图" });
  await expect(images.getByRole("img")).toHaveCount(2);
  for (const img of await preview.locator("img").all()) {
    await expect.poll(() => img.evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth)).toBe(1200);
  }
  await expect(images.getByRole("link", { name: "下载" }).first()).toHaveAttribute("download", "banner.png");

  // the chosen style is remembered
  await page.reload();
  await expect(page.getByTestId("xmly-style-cards")).toHaveAttribute("aria-checked", "true");
  await page.getByTestId("xmly-style-magazine").click();

  // plain text copy
  await page.evaluate(() => navigator.clipboard.writeText(""));
  await page.getByRole("button", { name: "复制纯文本" }).click();
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).not.toBe("");
  const text = (await page.evaluate(() => navigator.clipboard.readText())).replace(/\r\n/g, "\n");
  expect(text.split("\n\n").some((l) => TIME.test(l))).toBe(true);
});
