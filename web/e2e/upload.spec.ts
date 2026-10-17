import { expect, test } from "@playwright/test";

// default workspace; publish pack and cover come from scripted fake Claudes (tests/app/fake_claude.py)

test("上传喜马拉雅: says what is missing, then WAV, title, show notes and cover are one click away", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto("/");
  await expect(page).toHaveURL(/#\/ep\/.+\/listen/);
  const ep = decodeURIComponent(/#\/ep\/([^/]+)/.exec(page.url())![1]);
  const api = `/api/episodes/${encodeURIComponent(ep)}`;
  const idle = async (path: string) =>
    expect.poll(async () => (await (await page.request.get(`${api}/${path}`)).json()).job?.state ?? "none", { timeout: 30_000 }).not.toBe("running");

  await page.getByRole("link", { name: "上传喜马拉雅" }).click();
  await expect(page).toHaveURL(/\/upload$/);
  await expect(page.getByRole("heading", { name: "上传喜马拉雅" })).toBeVisible();
  await expect(page.getByRole("link", { name: /打开喜马拉雅创作中心/ })).toHaveAttribute("href", "https://studio.ximalaya.com/");

  // whatever earlier tests left: make sure all three exist
  expect((await page.request.post(`${api}/export`, { data: { formats: ["wav"] } })).ok()).toBe(true);
  await idle("export");
  if (!(await (await page.request.get(`${api}/publish`)).json()).pack) {
    await page.request.post(`${api}/publish/generate`);
    await idle("publish");
  }
  if (!(await (await page.request.get(`${api}/poster`)).json()).cover) {
    await page.request.post(`${api}/poster/generate`);
    await idle("poster");
    await page.request.post(`${api}/poster/v1/choose`);
    await idle("poster");
  }
  await page.reload();

  await expect(page.getByTestId("upload-summary")).toContainText("都准备好了");
  await expect(page.getByTestId("upload-wav")).toContainText(".wav");

  const pack = (await (await page.request.get(`${api}/publish`)).json()).pack;
  await expect(page.getByTestId("upload-title")).toHaveText(pack.title);
  await page.getByRole("button", { name: "复制标题" }).click();
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe(pack.title);
  await page.getByRole("button", { name: "复制 show notes" }).click();
  // Windows puts CRLF line endings on the plain-text clipboard
  await expect.poll(async () => (await page.evaluate(() => navigator.clipboard.readText())).replace(/\r\n/g, "\n")).toBe(pack.markdown);

  const wav = page.waitForEvent("download");
  await page.getByRole("link", { name: "下载 WAV" }).click();
  // (the saved name itself is Chromium's call: headless Linux falls back to "download" for Chinese names)
  expect((await wav).url()).toMatch(/\.wav$/);

  const img = page.getByRole("img", { name: "本期封面" });
  await expect.poll(() => img.evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth)).toBe(3000);
  const cover = page.waitForEvent("download");
  await page.getByRole("link", { name: "下载封面" }).click();
  const res = await page.request.get((await cover).url());
  expect(res.headers()["content-type"]).toBe("image/jpeg");
  expect(res.headers()["content-disposition"]).toContain(`${encodeURIComponent(ep)}_cover.jpg`);
});
