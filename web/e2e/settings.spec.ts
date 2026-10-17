import { expect, test } from "@playwright/test";

// import server (playwright.config.ts): runs as installed 2026.10.17.1, a local feed offers 2026.10.18.1
test.use({ baseURL: "http://127.0.0.1:8797" });

test("设置: new version offered → download (checksum checked) → ready to restart; key and machine status", async ({ page }) => {
  await page.goto("/#/settings");
  await expect(page.getByRole("heading", { name: "设置" })).toBeVisible();
  await expect(page.getByTestId("app-version")).toHaveText("2026.10.17.1");
  await page.getByRole("button", { name: "检查更新" }).click();
  const offer = page.getByTestId("update-available");
  await expect(offer).toContainText("2026.10.18.1");
  await expect(offer).toContainText("修了导出");
  await offer.getByRole("button", { name: "下载新版本" }).click();
  await expect(offer.getByRole("button", { name: "更新并重启" })).toBeEnabled();
  await expect(offer).toContainText("自动回到现在的版本");

  await expect(page.getByTestId("key-state")).toHaveText("没有设置");
  const save = page.getByRole("button", { name: "保存" });
  await expect(save).toBeDisabled();
  await page.getByLabel("API key", { exact: true }).fill("sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxxxx");
  await expect(save).toBeEnabled();
  await expect(page.getByTestId("ffmpeg-state")).toContainText("已就绪");

  // the top bar shows that an update is waiting
  await page.goto("/");
  await expect(page.getByRole("link", { name: /设置 · 有新版本/ })).toBeVisible();
});
