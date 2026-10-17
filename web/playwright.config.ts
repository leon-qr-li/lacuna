import { defineConfig, devices } from "@playwright/test";

const PORT = 8799;
const PYTHON = process.env.PYTHON ?? (process.platform === "win32" ? "python" : "python3");

export default defineConfig({
  testDir: "e2e",
  timeout: 45_000,
  workers: 1, // one shared backend; tests mutate its state
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    ...devices["Desktop Chrome"],
    viewport: { width: 1440, height: 960 },
    launchOptions: { args: ["--autoplay-policy=no-user-gesture-required"] },
  },
  webServer: {
    command: `${PYTHON} ../tests/app/serve_e2e.py ${PORT}`,
    url: `http://127.0.0.1:${PORT}/api/health`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
