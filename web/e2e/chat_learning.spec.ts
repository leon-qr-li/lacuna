import { expect, test } from "@playwright/test";

// "记住：……" in the AI producer chat becomes a candidate rule on 学到的规则 (no AI call)
test.use({ baseURL: "http://127.0.0.1:8798" });

test("chat 记住 → candidate rule in his words → 采用 → 撤回", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/#\/ep\/.+\/listen/);
  await page.getByLabel(/对 AI 制作人说/).fill("记住：Pei 的嗯都别删");
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("chat-log")).toContainText("记下了：「Pei 的嗯都别删」");
  await expect(page.getByTestId("proposal")).toHaveCount(0);

  await page.getByRole("link", { name: /学到的规则/ }).click();
  const rule = page.getByTestId("rule").filter({ hasText: "Pei 的嗯都别删" });
  await expect(rule).toContainText("你说过的");
  await expect(rule).toContainText("待你确认");
  await expect(rule).toContainText("下一集 AI 第一刀会照这条剪");
  await rule.getByText(/看例子/).click();
  await expect(rule).toContainText("的对话里说的");

  await rule.getByRole("button", { name: "采用", exact: true }).click();
  await expect(rule).toContainText("已生效");
  await rule.getByRole("button", { name: "撤回" }).click();
  await expect(rule).toContainText("不采用");
  await rule.getByRole("button", { name: "重新考虑" }).click();
  await expect(rule).toContainText("待你确认");
});
