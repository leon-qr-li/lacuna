import { expect, test } from "@playwright/test";

// 自动发布 即将推出 (decision 2026-10-23-auto-publish-coming-soon): 节目设置 → 发布 says it's coming, offers only the
// platforms LACUNA can surely reach (no 喜马拉雅 / 小宇宙), and keeps what the show picked for the admin's counts
test("自动发布: coming soon, four platforms, the pick is saved", async ({ page, request }) => {
  await page.goto("/#/project/publish");
  const box = page.getByTestId("show-auto-publish");
  await expect(box).toBeVisible();
  await expect(box).toContainText("即将推出");
  await expect(box.getByRole("checkbox")).toHaveCount(4);
  await expect(box).not.toContainText("喜马拉雅");
  await expect(box).not.toContainText("小宇宙");
  await expect(page.getByTestId("show-platforms")).toHaveCount(0);   // the old "where it's published" picker is gone
  await expect(box.getByTestId("auto-publish-feedback")).toHaveText("告诉我们");

  await box.getByTestId("auto-publish-apple").check();
  await box.getByTestId("auto-publish-amazon").check();
  await page.getByTestId("show-save").click();
  await expect(page.getByText("已保存")).toBeVisible();
  const s = await (await request.get("/api/show")).json();
  expect(s.publish.auto_wish).toEqual(["apple", "amazon"]);
  expect(s.publish.ximalaya).toBe(true);                           // Leon's 上传喜马拉雅 step stays

  await page.reload();
  await expect(page.getByTestId("auto-publish-apple")).toBeChecked();
  await expect(page.getByTestId("auto-publish-spotify")).not.toBeChecked();
  // leave the show as it was for the other tests
  await page.getByTestId("auto-publish-apple").uncheck();
  await page.getByTestId("auto-publish-amazon").uncheck();
  await page.getByTestId("show-save").click();
  await expect(page.getByText("已保存")).toBeVisible();
});
