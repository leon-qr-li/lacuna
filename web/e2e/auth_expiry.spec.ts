import { expect, test } from "@playwright/test";

// full scan 2026-10-18: uploads and voice input use their own fetch; a 401 there (session expired)
// only showed an inline error instead of bringing the sign-in screen back like every other call.
// The 401 is faked; we watch the sign-in check the app runs when it sees one.
test("a 401 from a library upload brings the sign-in check, like any other call", async ({ page }) => {
  let checks = 0;
  page.on("request", (r) => r.url().endsWith("/api/auth/status") && checks++);
  await page.route(/\/api\/library\/upload/, (route) => route.fulfill({ status: 401, json: { detail: "not signed in" } }));
  await page.goto("/#/library");
  await expect(page.getByLabel("选择音乐文件")).toBeAttached();
  const before = checks;
  await page.getByLabel("选择音乐文件").setInputFiles({ name: "x.wav", mimeType: "audio/wav", buffer: Buffer.alloc(64) });
  await expect.poll(() => checks, { timeout: 10_000 }).toBeGreaterThan(before);
  await page.unroute(/\/api\/library\/upload/);
});
