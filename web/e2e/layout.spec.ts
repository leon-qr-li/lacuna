import { expect, test } from "@playwright/test";

// phase 8 round 2: the AI producer owns the right column at full height and its text box is big enough to read
test("LACUNA: full-height column, multi-line box, grows (Shift+Enter = new line)", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await expect(page).toHaveURL(/#\/ep\/.+\/listen/, { timeout: 20_000 });
  const chat = page.getByRole("region", { name: "LACUNA 对话" });
  const box = await chat.boundingBox();
  expect(box!.width).toBeGreaterThanOrEqual(420);
  expect(box!.height).toBeGreaterThanOrEqual(600); // even with only the opening message

  const say = page.getByLabel(/对 LACUNA说/);
  const h0 = (await say.boundingBox())!.height;
  expect(h0).toBeGreaterThanOrEqual(60);
  await say.fill("第一行");
  await say.press("Shift+Enter");
  await say.pressSequentially("第二行");
  await expect(say).toHaveValue("第一行\n第二行");
  await say.fill("一\n二\n三\n四\n五");
  await expect.poll(async () => (await say.boundingBox())!.height).toBeGreaterThan(h0 + 30); // grows with the text
});
