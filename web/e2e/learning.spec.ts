import { expect, test } from "@playwright/test";

// the AI workspace is seeded with an earlier episode where Leon restored four of Pei's stumbles
test.use({ baseURL: "http://127.0.0.1:8798" });

test("learning: candidate rule from review decisions → 采用 → in force, survives reload → 撤回", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/#\/ep\/.+\/listen/); // a single episode opens directly
  const link = page.getByRole("link", { name: /学到的规则/ });
  await expect(link).toContainText("条待确认");
  await link.click();
  await expect(page).toHaveURL(/#\/learning/);
  await expect(page.getByRole("heading", { name: "学到的规则" })).toBeVisible();
  const rule = page.getByTestId("rule").filter({ hasText: "Pei的口误" });
  await expect(rule).toContainText("AI 删多了，以后少删");
  await expect(rule).toContainText("待你确认");
  await expect(rule).toContainText("下一集 AI 第一刀会照这条剪");
  await rule.getByText(/看例子/).click();
  await expect(rule).toContainText("对这也就就");

  await rule.getByRole("button", { name: "采用", exact: true }).click();
  await expect(rule).toContainText("已生效");
  await page.reload();
  const again = page.getByTestId("rule").filter({ hasText: "Pei的口误" });
  await expect(again).toContainText("已生效");
  await again.getByRole("button", { name: "撤回" }).click();
  await expect(again).toContainText("不采用");
  await again.getByRole("button", { name: "重新考虑" }).click();
  await expect(again).toContainText("待你确认");
});
