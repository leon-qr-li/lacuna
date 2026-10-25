import { expect, test } from "@playwright/test";

// On the shared server the staff cards (成员与邀请, 邮件发件人, AI 与专有名词) live in the admin site
// (decision 2026-10-24-admin-site): 设置 shows the owner a link to it instead. A local checkout keeps them.
const PW = "correct horse battery";

test.beforeEach(async ({ request }) => {
  await request.post("/api/auth/_test/reset?skip_setup=false");
});
test.afterEach(async ({ request }) => {
  await request.post("/api/auth/_test/reset?skip_setup=true");
});

test("设置 on the shared server: no staff cards, the owner gets a link to the admin", async ({ page }) => {
  expect((await page.request.post("/api/auth/register", { data: { email: "leon@example.com", password: PW } })).ok()).toBeTruthy();
  await page.goto("/#/settings");
  await expect(page.getByTestId("settings-nav-members")).toBeVisible();      // a local checkout: still here
  await expect(page.getByTestId("settings-admin-link")).toHaveCount(0);

  await page.route("**/api/app", async (route) => {
    const res = await route.fetch();
    await route.fulfill({ response: res, json: { ...(await res.json()), cloud: true, staging: false } });
  });
  await page.goto("/#/settings/members");
  await page.reload();
  await expect(page.getByTestId("settings-general")).toBeVisible();          // the old address falls back to 通用
  for (const id of ["members", "mail", "ai"]) await expect(page.getByTestId(`settings-nav-${id}`)).toHaveCount(0);
  const link = page.getByTestId("settings-admin-link");
  await expect(link).toHaveAttribute("href", /^https:\/\/admin\./);
  await expect(link).toHaveAttribute("target", "_blank");
});
