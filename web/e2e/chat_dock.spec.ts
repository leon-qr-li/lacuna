import { expect, test } from "@playwright/test";

// Leon 2026-10-20: 「收起」 sits on the LACUNA panel; once closed, a floating button at the bottom right brings it back
test("LACUNA: collapse on the panel, reopen from the floating button, remembered", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await expect(page).toHaveURL(/#\/ep\/.+\/listen/, { timeout: 20_000 });
  const chat = page.getByRole("region", { name: "LACUNA 对话" });
  const center = page.locator(".workspace > .center");
  await expect(chat).toBeVisible();
  await expect(page.getByTestId("chat-open")).toHaveCount(0);
  const narrow = (await center.boundingBox())!.width;

  // the button lives in the panel's header, at its top right
  const collapse = chat.getByRole("button", { name: "收起" });
  const cb = (await collapse.boundingBox())!;
  const pb = (await chat.boundingBox())!;
  expect(cb.y - pb.y).toBeLessThan(60);
  expect(pb.x + pb.width - (cb.x + cb.width)).toBeLessThan(40);
  await expect(page.locator(".topbar").getByRole("button", { name: /LACUNA/ })).toHaveCount(0);

  await collapse.click();
  await expect(chat).toBeHidden();
  await expect.poll(async () => (await center.boundingBox())!.width).toBeGreaterThan(narrow + 300); // editor takes the room, no rail left
  const fab = page.getByTestId("chat-open");
  const fb = (await fab.boundingBox())!;
  expect(1440 - (fb.x + fb.width)).toBeLessThan(48); // bottom right corner
  expect(900 - (fb.y + fb.height)).toBeLessThan(48);
  await expect(fab).toHaveCSS("position", "fixed");

  await page.reload(); // remembered
  await expect(page.getByTestId("chat-open")).toBeVisible({ timeout: 20_000 });
  await expect(chat).toBeHidden();
  // not shown on the other steps
  await page.getByRole("navigation", { name: "制作流程" }).getByRole("link", { name: /审阅改动/ }).click();
  await expect(page.getByTestId("chat-open")).toHaveCount(0);
  await page.getByRole("navigation", { name: "制作流程" }).getByRole("link", { name: "整集试听" }).click();

  await page.getByTestId("chat-open").click();
  await expect(chat).toBeVisible();
  await expect(page.getByTestId("chat-open")).toHaveCount(0);
});

test("LACUNA: on a narrow window the panel slides over from the right, not to the page bottom", async ({ page }) => {
  await page.setViewportSize({ width: 1000, height: 760 });
  await page.goto("/");
  await expect(page).toHaveURL(/#\/ep\/.+\/listen/, { timeout: 20_000 });
  const chat = page.getByRole("region", { name: "LACUNA 对话" });
  await expect(chat).toBeVisible();
  const b = (await chat.boundingBox())!;
  expect(b.y).toBeLessThan(40);
  expect(b.y + b.height).toBeLessThanOrEqual(760);
  expect(1000 - (b.x + b.width)).toBeLessThan(24);
  await chat.getByRole("button", { name: "收起" }).click();
  await expect(chat).toBeHidden();
  await expect(page.getByTestId("chat-open")).toBeVisible();
});
