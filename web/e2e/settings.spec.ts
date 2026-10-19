import { expect, test } from "@playwright/test";

// import server (playwright.config.ts): a development checkout, no VERSION file. The desktop app and its
// in-app update are retired (decision desktop-retired): 设置 shows the version, key and machine status only.
test.use({ baseURL: "http://127.0.0.1:8797" });

test("设置: version, key and machine status; no update controls", async ({ page }) => {
  await page.goto("/#/settings");
  await expect(page.getByRole("heading", { name: "设置" })).toBeVisible();
  await expect(page.getByTestId("app-version")).toHaveText("开发版");
  await expect(page.getByRole("button", { name: "检查更新" })).toHaveCount(0);
  await expect(page.getByTestId("update-available")).toHaveCount(0);

  await expect(page.getByTestId("key-state")).toHaveText("没有设置");
  const save = page.getByRole("button", { name: "保存" });
  await expect(save).toBeDisabled();
  await page.getByLabel("API key", { exact: true }).fill("sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxxxx");
  await expect(save).toBeEnabled();
  await expect(page.getByTestId("ffmpeg-state")).toContainText("已就绪");

  // the top-bar link is just 设置
  await page.goto("/");
  await expect(page.getByRole("link", { name: "设置", exact: true })).toBeVisible();
});
