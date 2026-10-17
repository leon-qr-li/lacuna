import { expect, test } from "@playwright/test";

// interface language: 设置 → 外观 → English reloads the page in English and is remembered; 中文 switches back
test("interface language: switch to English and back", async ({ page }) => {
  await page.goto("/#/settings");
  await page.evaluate(() => localStorage.removeItem("lacuna.lang"));
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("lang", "zh-CN");
  const group = page.getByRole("radiogroup", { name: "界面语言" });
  await expect(group.getByRole("radio", { name: "中文" })).toHaveAttribute("aria-checked", "true");

  await group.getByRole("radio", { name: "English" }).click();
  await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.getByRole("heading", { name: "Appearance" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Version" })).toBeVisible();
  // the server gets the choice too (errors and AI replies follow it)
  expect((await page.context().cookies()).find((c) => c.name === "lacuna_lang")?.value).toBe("en");

  // remembered on the other screens
  await page.goto("/#/");
  await expect(page.getByRole("heading", { name: "Episodes" })).toBeVisible();
  await expect(page.getByText("Import an episode").first()).toBeVisible();
  await expect(page.getByRole("link", { name: /^Settings/ })).toBeVisible();
  await page.locator(".ep-list a").first().click();
  const steps = page.getByRole("navigation", { name: "Production steps" });
  await expect(steps).toContainText("Review edits");
  await expect(steps).toContainText("Listen");
  await expect(steps).toContainText("Export");
  await expect(page.getByRole("button", { name: /Undo/ })).toBeVisible();
  await expect(page.getByRole("region", { name: "Player" })).toBeVisible();
  await expect(page.getByRole("region", { name: "AI producer chat" })).toContainText("First cut");
  await page.getByRole("link", { name: /Review edits/ }).click();
  await expect(page.getByRole("heading", { name: /For you to review/ })).toBeVisible();
  await page.getByRole("link", { name: /Music/ }).first().click();
  await expect(page.getByRole("heading", { name: "Music", exact: true })).toBeVisible();

  // and back
  await page.goto("/#/settings");
  await page.getByRole("radiogroup", { name: "Language" }).getByRole("radio", { name: "中文" }).click();
  await expect(page.getByRole("heading", { name: "设置", exact: true })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", "zh-CN");
});
