import { expect, test } from "@playwright/test";

// voice input in the chat: Chromium's fake mic (a beep, see playwright.config.ts) records a real
// MediaRecorder clip, the server really decodes it with ffmpeg, and a fake recogniser "hears"
// 这句删掉 (tests/app/serve_e2e.py --ai); the text then goes through the normal Claude chat
test.use({ baseURL: "http://127.0.0.1:8798", permissions: ["microphone"] });

test("voice input: talk, stop, text lands in the box, send as usual", async ({ page }) => {
  // don't wait for "load": the episode <audio> holds it until its WAV metadata arrives, which on a
  // slow macOS runner after earlier tests changed the cut can take most of the timeout; the mic
  // doesn't need the audio
  await page.goto("/", { waitUntil: "domcontentloaded" });
  const mic = page.getByTestId("mic");
  await expect(mic).toBeEnabled();
  await expect(mic).toHaveAttribute("title", /本机识别/);
  const box = page.getByLabel(/对 AI 制作人说/);
  await box.fill("嗯");

  await mic.click();
  await expect(mic).toHaveAttribute("aria-pressed", "true");
  await expect(mic).toContainText("● 0:0");
  await page.waitForTimeout(1500);
  await mic.click();
  await expect(box).toHaveValue("嗯 这句删掉"); // appended to what was typed, not sent yet
  await expect(mic).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByTestId("proposal")).toHaveCount(0);

  await box.fill("这句删掉");
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("proposal")).toBeVisible();
  await page.getByTestId("proposal").getByRole("button", { name: "再改" }).click();
});
