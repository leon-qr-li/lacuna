import { expect, test } from "@playwright/test";

const SHOTS = process.env.LESSONS_SHOTS; // folder for review screenshots (optional)

// 「记住」 in the AI producer chat (首次检测 #9): LACUNA first says how it read the ask; nothing is stored
// as a rule until 记住这条. 改一下 sends a correction, 不用 stores nothing.
test.use({ baseURL: "http://127.0.0.1:8798" });

test("chat 记住 → LACUNA's reading → 改一下 → 记住这条 → in force → 撤回", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/#\/ep\/.+\/listen/, { timeout: 20_000 });
  const remember = page.getByRole("button", { name: "记住", exact: true });
  await expect(remember).toBeDisabled(); // nothing typed yet
  await page.getByLabel(/对 LACUNA ?说/).fill("Pei 的嗯都别删");
  await remember.click();
  const card = page.getByTestId("remember-card").last();
  await expect(card).toContainText("我理解的是：以后每一集剪的时候都按「Pei 的嗯都别删」来");
  await expect(card.getByTestId("remember-rule")).toHaveText("每一期都照做：Pei 的嗯都别删"); // never his raw words
  await expect(card).toContainText("是否记住这条？");
  await expect(page.getByTestId("proposal")).toHaveCount(0);
  await expect(page.getByLabel(/对 LACUNA ?说/)).toHaveValue("");

  // not stored yet
  const titles = async () =>
    ((await (await page.request.get("/api/learning")).json()).rules as { title: string }[]).map((r) => r.title);
  expect((await titles()).filter((x) => x.includes("Pei 的嗯都别删"))).toEqual([]);

  await page.getByLabel(/对 LACUNA ?说/).fill("记住：开头那段闲聊别剪");
  await page.getByRole("button", { name: "发送" }).click();
  const card2 = page.getByTestId("remember-card").last();
  await expect(card2.getByTestId("remember-rule")).toHaveText("每一期都照做：开头那段闲聊别剪");
  await card2.getByRole("button", { name: "改一下" }).click();
  await card2.getByRole("textbox", { name: "告诉 LACUNA 这条规则要怎么改" }).fill("只针对 Pei");
  await card2.getByRole("button", { name: "发给 LACUNA" }).click();
  await expect(card2.getByTestId("remember-rule")).toHaveText("每一期都照做：开头那段闲聊别剪（只针对 Pei）");
  await expect(card2).toContainText("我按你说的改了：只针对 Pei。");
  await expect(card2).toContainText("改过的规则");
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/remember_card.png` });
  await card2.getByRole("button", { name: "记住这条" }).click();
  await expect(card2).toContainText("记住了，已生效");
  await expect(card2.getByRole("button")).toHaveCount(0);

  const first = page.getByTestId("remember-card").filter({ hasText: "Pei 的嗯都别删" });
  await first.getByRole("button", { name: "不用" }).click();
  await expect(first).toContainText("这条不记");
  expect((await titles()).filter((x) => x.includes("Pei 的嗯都别删"))).toEqual([]);

  await card2.getByRole("link", { name: /学到的规则/ }).click();
  await page.getByRole("tab", { name: /已生效/ }).click();
  const rule = page.getByTestId("rule").filter({ hasText: "开头那段闲聊别剪（只针对 Pei）" });
  await expect(rule).toContainText("你说过的");
  await expect(rule).toContainText("已生效");
  await rule.getByText(/看例子/).click();
  await expect(rule).toContainText("记住：开头那段闲聊别剪"); // his words are the evidence
  await expect(page.getByTestId("rule").filter({ hasText: "Pei 的嗯都别删" })).toHaveCount(0);
  await rule.getByRole("button", { name: "撤回" }).click();
  await page.getByRole("tab", { name: /已不采用/ }).click();
  await expect(rule).toContainText("已不采用");
});
