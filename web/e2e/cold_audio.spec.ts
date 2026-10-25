import { expect, test } from "@playwright/test";

// An episode not opened for 14 days has its audio in cloud storage (lacuna_app/cold.py): opening it shows
// 「正在取回这一集的音频」 with the progress while the server answers 423, then the episode opens by itself.
// The server side is covered by tests/app/test_cold.py; here the answers are routed.
const ID = "EP_TEST_合成";
const EP = `/api/episodes/${encodeURIComponent(ID)}`;

test("an old episode's audio comes back from cloud storage, then the episode opens", async ({ page }) => {
  const steps = [0.2, 0.7];
  let release = false;
  await page.route((u) => u.pathname === EP, async (route) => {
    if (!release) {
      const p = steps.length > 1 ? steps.shift()! : steps[0];
      return route.fulfill({ status: 423, json: { detail: "正在取回这一集的音频…", restoring: { progress: p, failed: false } } });
    }
    await route.fallback();
  });
  await page.goto(`/#/ep/${encodeURIComponent(ID)}/review`);
  const box = page.getByTestId("audio-restoring");
  await expect(box).toContainText("正在取回这一集的音频");
  await expect(box).toContainText("70%");
  await expect(box).toContainText("10–30 秒");
  release = true;
  await expect(box).toBeHidden({ timeout: 10_000 });
  await expect(page.getByTestId("main-audio")).toBeAttached();
  await expect(page.locator(".error")).toHaveCount(0);
});

test("a failed restore says so instead of spinning forever", async ({ page }) => {
  await page.route((u) => u.pathname === EP, (route) =>
    route.fulfill({ status: 423, json: { detail: "取回音频没有成功，请稍后再打开这一集。", restoring: { progress: 0.1, failed: true } } }),
  );
  await page.goto(`/#/ep/${encodeURIComponent(ID)}/review`);
  await expect(page.getByText("取回音频没有成功")).toBeVisible();
});
