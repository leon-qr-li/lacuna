import { defineConfig, devices } from "@playwright/test";

const PORT = 8799;
export const AI_PORT = 8798;
export const IMPORT_PORT = 8797;
export const SCOPES_PORT = 8796;
const PYTHON = process.env.PYTHON ?? (process.platform === "win32" ? "python" : "python3");

export default defineConfig({
  testDir: "e2e",
  timeout: 45_000,
  workers: 1, // one shared backend; tests mutate its state
  // CI retries a failed test once, so a timing hiccup doesn't block a deploy; a real bug fails twice.
  // Playwright still lists a test that passed only on retry as "flaky" in the report.
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    ...devices["Desktop Chrome"],
    viewport: { width: 1440, height: 960 },
    launchOptions: {
      // fake mic (a beep) for the voice-input test; the permission is granted per test
      args: ["--autoplay-policy=no-user-gesture-required", "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"],
    },
  },
  webServer: [
    {
      command: `${PYTHON} ../tests/app/serve_e2e.py ${PORT}`,
      url: `http://127.0.0.1:${PORT}/api/health`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      // a workspace holding one AI first-cut episode (see tests/app/synth.py make_ai_workspace)
      command: `${PYTHON} ../tests/app/serve_e2e.py ${AI_PORT} --ai`,
      url: `http://127.0.0.1:${AI_PORT}/api/health`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      // empty workspace + two raw tracks; fake ASR and fake Claude first cut (phase 4 import)
      command: `${PYTHON} ../tests/app/serve_e2e.py ${IMPORT_PORT} --import`,
      url: `http://127.0.0.1:${IMPORT_PORT}/api/health`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      // the default workspace plus a second episode (tests/app/e2e/library_scopes.py): library scopes
      command: `${PYTHON} ../tests/app/serve_e2e.py ${SCOPES_PORT}`,
      url: `http://127.0.0.1:${SCOPES_PORT}/api/health`,
      env: { LACUNA_E2E_SECOND_EPISODE: "1" },
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
