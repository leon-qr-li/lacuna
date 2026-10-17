import { expect, test } from "@playwright/test";

// default workspace; publish pack and covers are drawn by scripted fake Claudes (tests/app/fake_claude.py)

test("cover: needs the publish pack → draw 4 versions → zoom → change one with a sentence → choose", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/#\/ep\/.+\/listen/);
  await page.getByRole("link", { name: "海报" }).click();
  await expect(page).toHaveURL(/\/poster$/);
  await expect(page.getByRole("heading", { name: "海报" })).toBeVisible();
  await expect(page.getByTestId("poster-needs-pack")).toBeVisible();
  await expect(page.getByRole("button", { name: "画 4 版海报" })).toBeDisabled();

  // the publish pack (phase 9) gives the title / blurb the cover is drawn from
  const ep = decodeURIComponent(/#\/ep\/([^/]+)/.exec(page.url())![1]);
  const api = `/api/episodes/${encodeURIComponent(ep)}`;
  expect((await page.request.post(`${api}/publish/generate`)).ok()).toBe(true);
  await expect.poll(async () => (await (await page.request.get(`${api}/publish`)).json()).pack !== null).toBe(true);
  await page.reload();

  await expect(page.getByText(/约 \$1/)).toBeVisible();
  await page.getByRole("button", { name: "画 4 版海报" }).click();
  await expect(page.getByTestId("poster-running")).toBeVisible();
  const cards = page.getByTestId("poster-card");
  await expect(cards).toHaveCount(4, { timeout: 15_000 });
  for (const label of ["一个意象", "并置", "色块与几何", "自由发挥"]) {
    await expect(cards.filter({ hasText: label })).toHaveCount(1);
  }
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
  await emblem.getByRole("button", { name: "改", exact: true }).click();
  await expect(cards).toHaveCount(5, { timeout: 15_000 });
  await expect(cards.first()).toContainText("按你的话改");
  await expect(cards.first()).toContainText("「换成暖色」");

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
});
