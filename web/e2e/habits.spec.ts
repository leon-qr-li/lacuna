import { expect, test } from "@playwright/test";
import { scan } from "./contrast-scan";

// 设置 → 剪辑习惯 (the editor's own 剪辑力度, for every project) and, per host in 项目设置, 更狠 / 一样 / 更松.
const reset = async ({ request }: { request: import("@playwright/test").APIRequestContext }) => {
  await request.put("/api/habits", { data: { cut_level: "normal" } });
};
test.beforeEach(reset);
test.afterEach(reset);

for (const theme of ["light", "dark"] as const) {
  test(`editing habits in settings (${theme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme });
    await page.goto("/#/settings/edit");
    await page.evaluate((t) => localStorage.setItem("lacuna.theme", t), theme);
    await page.reload();
    const card = page.getByTestId("habits-card");
    await expect(card).toContainText("包括别人邀请你协作的节目");
    await expect(card.getByRole("radio", { name: "正常" })).toHaveAttribute("aria-checked", "true");
    // the button turns on at once; the reload below must wait until the server has saved it
    const saved = page.waitForResponse((r) => r.url().endsWith("/api/habits") && r.request().method() === "PUT");
    await card.getByRole("radio", { name: "多剪" }).click();
    await expect(card.getByRole("radio", { name: "多剪" })).toHaveAttribute("aria-checked", "true");
    expect((await saved).ok()).toBeTruthy();
    expect((await scan(page)).bad).toEqual([]);
    await page.reload();
    await expect(page.getByTestId("habits-card").getByRole("radio", { name: "多剪" })).toHaveAttribute("aria-checked", "true");
    // the link opens 学到的规则 on its 已生效 tab
    await card.getByRole("link", { name: "去看学到的规则" }).click();
    await expect(page.getByRole("tab", { name: /已生效/ })).toHaveAttribute("aria-selected", "true");
  });
}

test("hosts are set relative to the editor's level", async ({ page, request }) => {
  const show = await (await request.get("/api/show")).json();
  expect(show.cut_adjusts).toEqual(["less", "same", "more"]);
  expect(show.hosts.every((h: { cut_adjust?: string }) => !!h.cut_adjust)).toBe(true);
  await page.goto("/#/project/hosts");
  const pick = page.getByTestId("host-adjust").first();
  await expect(pick).toBeVisible();
  await expect(pick.locator("option")).toHaveText(["比我平时多剪", "和我平时一样", "比我平时少剪"]);
  await expect(page.getByRole("link", { name: "我平时的剪辑力度" }).first()).toHaveAttribute("href", "#/settings/edit");
});

test("editing habits in English", async ({ page }) => {
  await page.goto("/#/settings/edit");
  await page.evaluate(() => localStorage.setItem("lacuna.lang", "en"));
  await page.reload();
  const card = page.getByTestId("habits-card");
  await expect(card.getByRole("heading")).toHaveText("Editing habits");
  await expect(card.getByRole("radio", { name: "Firm" })).toBeVisible();
  await page.evaluate(() => localStorage.removeItem("lacuna.lang"));
});
