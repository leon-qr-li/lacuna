import { expect, test } from "@playwright/test";

// the AI first-cut server (playwright.config.ts) answers chat through ClaudeEditorAdapter with a
// scripted fake client (tests/app/fake_claude.py): the real request/resolve path, no network
test.use({ baseURL: "http://127.0.0.1:8798" });

test("chat with Claude: badge, cut the sentence at the playhead, cost line, approve, restore", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("editor-badge")).toHaveText("LACUNA");
  await expect(page.getByTestId("chat-log")).not.toContainText("演示规则");
  await expect(page.getByLabel(/对 AI 制作人说/)).toHaveAttribute("placeholder", /跑题了删掉/);

  await page.getByRole("slider", { name: "播放位置" }).fill("33");
  await page.getByLabel(/对 AI 制作人说/).fill("这句删掉");
  await page.keyboard.press("Enter");
  const proposal = page.getByTestId("proposal");
  await expect(proposal).toBeVisible();
  await expect(page.getByTestId("chat-log")).toContainText(/删掉 (Leon|Pei) 这句「.+」/);
  await expect(page.getByTestId("usage").last()).toContainText(/LACUNA · \d+\.\d 秒 · ≈\$0\.0\d\d/);
  const clock = page.getByTestId("clock");
  const total = (await clock.textContent())!.split("/")[1].trim(); // "m:ss" length of the cut
  await proposal.getByRole("button", { name: "批准" }).click();
  await expect(page.getByText("✓ 已批准并应用")).toBeVisible();
  await expect(page.locator('[data-testid=nearby] li[data-source="chat"]')).toHaveCount(1);
  await expect(clock).not.toContainText(`/ ${total}`);

  // "恢复" brings the chat cut back as a proposal
  await page.getByLabel(/对 AI 制作人说/).fill("把刚才删的恢复");
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("chat-log")).toContainText("恢复成原话");
  await page.getByTestId("proposal").getByRole("button", { name: "批准" }).click();
  await expect(clock).toContainText(`/ ${total}`);
});
