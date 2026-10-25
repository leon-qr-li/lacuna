import { expect, test } from "@playwright/test";

// the AI workspace is seeded with an earlier episode where Leon restored four of Pei's stumbles
test.use({ baseURL: "http://127.0.0.1:8798" });

test("learning: candidate rule from review decisions → 采用 → in force, survives reload → 撤回", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/#\/ep\/.+\/listen/, { timeout: 20_000 }); // a single episode opens directly (first page of a cold server on Windows CI can take >5 s)
  const link = page.getByRole("link", { name: /^学到的规则/ });
  await expect(link).toContainText("条待确认");
  await link.click();
  await expect(page).toHaveURL(/#\/learning/);
  await expect(page.getByRole("heading", { name: "学到的规则" })).toBeVisible();
  const rule = page.getByTestId("rule").filter({ hasText: "Pei的口误" });
  await expect(rule).toContainText("AI 删多了，以后少删");
  await expect(rule).toContainText("待你确认");
  await expect(rule).toContainText("下一集 LACUNA 初剪会照这条剪");
  await rule.getByText(/看例子/).click();
  await expect(rule).toContainText("对这也就就");

  // by default only rules waiting for a decision show; a decided one moves to its own group
  await expect(page.getByRole("tab", { name: /待你决定/ })).toHaveAttribute("aria-selected", "true");
  await rule.getByRole("button", { name: "采用", exact: true }).click();
  await expect(rule).toHaveCount(0);
  await expect(page.getByRole("status")).toContainText("在「已生效」里能找到");
  await page.getByRole("status").getByRole("button", { name: "去看看" }).click();
  await expect(page.getByRole("tab", { name: /已生效/ })).toHaveAttribute("aria-selected", "true");
  await expect(rule).toContainText("已生效");

  await page.reload();
  await expect(page.getByRole("tab", { name: /待你决定/ })).toHaveAttribute("aria-selected", "true");
  const again = page.getByTestId("rule").filter({ hasText: "Pei的口误" });
  await expect(again).toHaveCount(0);
  await page.getByRole("tab", { name: /已生效/ }).click();
  await expect(again).toContainText("已生效");
  await again.getByRole("button", { name: "撤回" }).click();
  await expect(again).toHaveCount(0);
  await page.getByRole("tab", { name: /已不采用/ }).click();
  await expect(again).toContainText("已不采用");
  await again.getByRole("button", { name: "重新考虑" }).click();
  await page.getByRole("tab", { name: /待你决定/ }).click();
  await expect(again).toContainText("待你确认");

  // a rejected rule can be deleted for good (two steps); it stays gone after the page re-learns
  await again.getByRole("button", { name: "不采用", exact: true }).click();
  await page.getByRole("tab", { name: /已不采用/ }).click();
  await again.getByRole("button", { name: "删除", exact: true }).click();
  await again.getByRole("button", { name: "取消" }).click();
  await expect(again).toBeVisible();
  await again.getByRole("button", { name: "删除", exact: true }).click();
  await again.getByRole("button", { name: "确定删除" }).click();
  await expect(again).toHaveCount(0);
  await expect(page.getByRole("status")).toContainText("以后不会再出现");
  await page.reload();
  for (const g of [/待你决定/, /已生效/, /已不采用/]) {
    await page.getByRole("tab", { name: g }).click();
    await expect(page.getByTestId("rule").filter({ hasText: "Pei的口误" })).toHaveCount(0);
  }
});

// many rules: each group pages 10 at a time (the overview is stubbed so the counts are known)
test("learning: groups count, filter and page through many rules", async ({ page }) => {
  const rule = (i: number, state: string) => ({
    id: `r${i}`, kind: "protect", title: `规则${String(i).padStart(2, "0")}`, detail: "细节", prompt: "", key: {}, evidence: {},
    examples: [], policy: null, state, updated: false, approved_at: null,
  });
  const rules = [
    ...Array.from({ length: 23 }, (_, i) => rule(i, "candidate")),
    ...Array.from({ length: 3 }, (_, i) => rule(30 + i, "approved")),
    rule(40, "rejected"),
  ];
  const stats = { episodes: ["EP001"], decisions: 0, considered: 0, kept: 0, restored: 0, accepted: 0, declined: 0, added: 0, untouched: 0 };
  await page.route("**/api/learning", (r) => r.fulfill({ json: { rules, pending: 23, stats } }));
  await page.goto("/#/learning");
  await expect(page.getByRole("tab", { name: /待你决定/ })).toContainText("23");
  await expect(page.getByRole("tab", { name: /已生效/ })).toContainText("3");
  await expect(page.getByRole("tab", { name: /已不采用/ })).toContainText("1");
  const cards = page.getByTestId("rule");
  await expect(cards).toHaveCount(10);
  await expect(cards.first()).toContainText("规则00");
  await expect(page.getByText("第 1–10 条，共 23 条")).toBeVisible();
  await expect(page.getByRole("button", { name: "上一页" })).toBeDisabled();
  await page.getByRole("button", { name: "3", exact: true }).click();
  await expect(cards).toHaveCount(3);
  await expect(cards.first()).toContainText("规则20");
  await expect(page.getByRole("button", { name: "下一页" })).toBeDisabled();
  await page.getByRole("button", { name: "上一页" }).click();
  await expect(cards.first()).toContainText("规则10");

  await page.getByRole("tab", { name: /已生效/ }).click();
  await expect(cards).toHaveCount(3);
  await expect(page.getByRole("navigation", { name: "翻页" })).toHaveCount(0); // one page: no pager
  await page.getByRole("tab", { name: /已不采用/ }).click();
  await expect(cards).toHaveCount(1);
  await expect(cards).toContainText("规则40");
});
