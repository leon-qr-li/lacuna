import { expect, test } from "@playwright/test";

// V6: when the AI call behind 「记住」 fails, the card says so in plain words (never "not connected",
// never the raw API error) and still offers his own words to confirm or change.
test.use({ baseURL: "http://127.0.0.1:8798" });

test("记住 with a failing AI → readable reason, his words to confirm", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/#\/ep\/.+\/listen/, { timeout: 20_000 });
  await page.getByLabel(/对 LACUNA说/).fill("记住：AI 出错测试 片尾别剪");
  await page.getByRole("button", { name: "发送" }).click();
  const card = page.getByTestId("remember-card").filter({ hasText: "AI 出错测试" });
  await expect(card.getByTestId("remember-rule")).toHaveText("AI 出错测试 片尾别剪");
  await expect(card).toContainText("这次没能改写（LACUNA 暂时出了点问题）");
  await expect(card).not.toContainText("没接上");
  await expect(card).not.toContainText("network");
  await expect(card.getByRole("button", { name: "记住这条" })).toBeVisible();
});
