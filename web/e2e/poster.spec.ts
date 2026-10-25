import { expect, test } from "@playwright/test";

// default workspace; publish pack and covers are drawn by scripted fake Claudes (tests/app/fake_claude.py)

test("cover: needs the publish pack → draw 4 versions → zoom → change one with a sentence → choose", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/#\/ep\/.+\/listen/, { timeout: 20_000 });
  await page.getByRole("link", { name: "发布", exact: true }).click(); // 发布 step → sub-tabs
  await page.getByRole("link", { name: "封面", exact: true }).click();
  await expect(page).toHaveURL(/\/poster$/);
  await expect(page.getByRole("heading", { name: "封面" })).toBeVisible();
  await expect(page.getByTestId("poster-needs-pack")).toBeVisible();
  await expect(page.getByRole("button", { name: "画 4 版封面" })).toBeDisabled();

  // the publish pack (phase 9) gives the title / blurb the cover is drawn from
  const ep = decodeURIComponent(/#\/ep\/([^/]+)/.exec(page.url())![1]);
  const api = `/api/episodes/${encodeURIComponent(ep)}`;
  expect((await page.request.post(`${api}/publish/generate`)).ok()).toBe(true);
  await expect.poll(async () => (await (await page.request.get(`${api}/publish`)).json()).pack !== null).toBe(true);
  await page.reload();

  // included in the plan: no price anywhere, a few rounds per episode instead
  await expect(page.getByText("每集可以画 3 轮")).toBeVisible();
  await expect(page.locator("main.poster")).not.toContainText("$");
  await page.getByRole("button", { name: "画 4 版封面" }).click();
  await expect(page.getByTestId("poster-running")).toBeVisible();
  const cards = page.getByTestId("poster-card");
  await expect(cards).toHaveCount(4, { timeout: 15_000 });
  await expect(page.locator("main.poster")).not.toContainText("$");
  for (const label of ["一个意象", "并置", "色块与几何", "自由发挥"]) {
    await expect(cards.filter({ hasText: label })).toHaveCount(1);
  }
  // 2×2: two per row, the third starts a second row; one per row on a narrow window
  const boxes = async () => Promise.all([0, 1, 2, 3].map(async (i) => (await cards.nth(i).boundingBox())!));
  let [a, b, c, d4] = await boxes();
  expect(Math.abs(a.y - b.y)).toBeLessThan(2);
  expect(b.x).toBeGreaterThan(a.x + a.width - 1);
  expect(c.y).toBeGreaterThan(a.y + a.height - 1);
  expect(Math.abs(c.x - a.x)).toBeLessThan(2);
  expect(Math.abs(d4.y - c.y)).toBeLessThan(2);
  expect(a.width).toBeGreaterThan(400);
  // the 一句话改 box takes (nearly) the card's whole width, with mic and 改 inside the same bar
  const bar = cards.first().getByTestId("poster-revise");
  const box = (await bar.getByRole("textbox").boundingBox())!;
  expect(box.width).toBeGreaterThan(a.width * 0.8);
  await expect(bar.getByTestId("mic")).toBeVisible();
  await expect(bar.getByRole("button", { name: "改", exact: true })).toBeDisabled();
  await expect(bar).toContainText("Shift+Enter");
  await page.setViewportSize({ width: 700, height: 900 });
  [a, b] = await boxes();
  expect(Math.abs(a.x - b.x)).toBeLessThan(2);
  expect(b.y).toBeGreaterThan(a.y + a.height - 1);
  await page.setViewportSize({ width: 1440, height: 960 });

  // previews are real PNGs rendered on this machine
  const img = cards.first().locator("img");
  await expect.poll(() => img.evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth)).toBe(1000);

  // zoom in and out
  await cards.first().getByTitle("看大图").click();
  await expect(page.getByRole("dialog", { name: "大图" })).toBeVisible();
  await page.getByRole("dialog", { name: "大图" }).click();
  await expect(page.getByRole("dialog", { name: "大图" })).toBeHidden();

  // one sentence → a new version on top, linked to the one it came from
  const emblem = cards.filter({ hasText: "一个意象" });
  await emblem.getByRole("textbox").fill("换成暖色");
  await expect(emblem.getByRole("button", { name: "改", exact: true })).toBeEnabled();
  await emblem.getByRole("textbox").press("Enter"); // Enter sends (same as clicking 改)
  await expect(cards).toHaveCount(5, { timeout: 15_000 });
  await expect(cards.first()).toContainText("按你的话改");
  await expect(cards.first()).toContainText("「换成暖色」");
  await expect(emblem.getByRole("textbox")).toHaveValue(""); // sent text clears the box

  // choose it: 3000×3000 cover files in the publish folder
  await cards.first().getByRole("button", { name: "用这张" }).click();
  const cover = page.getByTestId("poster-cover");
  await expect(cover).toBeVisible({ timeout: 30_000 });
  await expect(cover).toContainText("3000×3000");
  await expect(cover).toContainText("cover.jpg");
  await expect(cards.first().getByRole("button", { name: "正在用这张" })).toBeDisabled();
  const d = await (await page.request.get(`${api}/poster`)).json();
  expect(d.cover.jpg).toMatch(/cover\.jpg$/);

  // survives a reload
  await page.reload();
  await expect(page.getByTestId("poster-cover")).toBeVisible();
  await expect(page.getByTestId("poster-card")).toHaveCount(5);

  // on the cloud server: no server folder or 打开文件夹, the cover downloads from the page instead (regression, batch 8)
  await page.route("**/api/auth/status", async (route) => {
    const res = await route.fetch();
    await route.fulfill({ response: res, json: { ...(await res.json()), cloud: true } });
  });
  await page.reload();
  const cloudCover = page.getByTestId("poster-cover");
  await expect(cloudCover).toContainText("各个播客平台都能用");
  await expect(cloudCover).not.toContainText("cover.png");
  await expect(cloudCover.getByRole("button", { name: "打开文件夹" })).toHaveCount(0);
  await expect(cloudCover.locator(".mono")).toHaveCount(0);
  const dl = page.getByTestId("poster-download");
  const jpg = await page.request.get((await dl.getAttribute("href"))!);
  expect(jpg.headers()["content-type"]).toBe("image/jpeg");
  await page.unroute("**/api/auth/status");

  // the home page's episode tile now shows the chosen cover instead of the letter
  await page.goto("/#/");
  await page.reload();
  const tile = page.getByTestId("episode-poster").first();
  await expect(tile).toBeVisible();
  await expect(tile).toHaveAttribute("src", new RegExp(`/poster/${d.chosen}\\.png`));
  expect(await tile.evaluate((e: HTMLImageElement) => e.naturalWidth)).toBeGreaterThan(0);
});
