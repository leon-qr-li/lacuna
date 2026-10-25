import { expect, test } from "@playwright/test";

// voice input in the chat: Chromium's fake mic (a beep, see playwright.config.ts) records a real
// MediaRecorder clip, the server really decodes it with ffmpeg, and a fake recogniser "hears"
// 陪说这句删掉, and a fake context pass fixes 陪 → Pei only when the page sent the episode
// (tests/app/e2e/dictation.py); the text then goes through the normal chat
test.use({ baseURL: "http://127.0.0.1:8798", permissions: ["microphone"] });

test("voice input: talk, stop, text lands in the box, send as usual", async ({ page }) => {
  // don't wait for "load": the episode <audio> holds it until its WAV metadata arrives, which on a
  // slow macOS runner after earlier tests changed the cut can take most of the timeout; the mic
  // doesn't need the audio
  await page.goto("/", { waitUntil: "domcontentloaded" });
  const mic = page.getByTestId("mic");
  await expect(mic).toBeEnabled();
  await expect(mic).toHaveAttribute("title", /LACUNA 服务器上识别/);
  const box = page.getByLabel(/对 LACUNA ?说/);
  await box.fill("嗯");

  await mic.click();
  await expect(mic).toHaveAttribute("aria-pressed", "true");
  await expect(mic).toContainText("● 0:0");
  await page.waitForTimeout(1500);
  await mic.click();
  await expect(box).toHaveValue("嗯 Pei说这句删掉"); // name fixed from context, appended, not sent yet
  await expect(mic).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByTestId("proposal")).toHaveCount(0);

  await box.fill("这句删掉");
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("proposal")).toBeVisible();
  await page.getByTestId("proposal").getByRole("button", { name: "再改" }).click();
});
