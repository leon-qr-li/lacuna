import { expect, test } from "@playwright/test";

// English engine: the show's language (项目设置) is the import form's default; each import can change it.
test("show language: English becomes the import form's default", async ({ page }) => {
  await page.goto("/#/project");
  const lang = page.getByTestId("show-language");
  await expect(lang).toHaveValue("zh");
  await lang.selectOption("en");
  await page.getByTestId("show-save").click();
  await expect(page.getByText("已保存")).toBeVisible();
  expect((await (await page.request.get("/api/show")).json()).language).toBe("en");

  await page.goto("/#/");
  await page.getByRole("button", { name: "导入新一集" }).click();
  const pick = page.getByTestId("import-language");
  await expect(pick).toHaveValue("en");
  await expect(pick.locator("option")).toHaveText(["中文", "英文"]);
  await page.getByRole("button", { name: "取消" }).click();

  // back to Chinese so the other specs see Leon's show as it was
  await page.goto("/#/project");
  await page.getByTestId("show-language").selectOption("zh");
  await page.getByTestId("show-save").click();
  await expect(page.getByText("已保存")).toBeVisible();
  expect((await (await page.request.get("/api/show")).json()).language).toBe("zh");
});
