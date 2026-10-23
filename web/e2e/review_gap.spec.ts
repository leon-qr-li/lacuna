import { expect, test } from "@playwright/test";

// 审阅改动: the list and the card sit right under the progress bar, with no empty band above them
test.use({ baseURL: "http://127.0.0.1:8798" });

test("no empty space above the review content on a tall window", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto("/");
  await page.getByRole("link", { name: /审阅改动/ }).click();
  const top = (await page.getByTestId("review-progress").boundingBox())!;
  const list = (await page.getByTestId("review-list").boundingBox())!;
  expect(list.y - (top.y + top.height)).toBeLessThan(60);
});
