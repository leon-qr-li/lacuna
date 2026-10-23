# CI runs on Linux only; E2E retries once in CI

Date: 2026-10-23. Chosen by Leon (decision card), after a Windows-only E2E flake held a deploy.

- pytest and both E2E shards run on `ubuntu-latest` only. Windows and macOS are gone from the matrix:
  the product runs only in the cloud image (Linux) and the desktop app is retired
  (`2026-10-19-desktop-retired.md`), so those runs tested nothing users get. They were also the slowest
  jobs and the source of almost every flaky failure (auth TOTP step, tour restart, levels compare).
- Playwright retries a failed test once in CI (`retries: process.env.CI ? 1 : 0`). A real bug fails
  twice; a test that passed only on retry is still listed as flaky in the report. Local runs don't retry.
- Kept: the Playwright suite itself. It is the only automated check of the UI (tour, timeline, review
  keys) and of the brand-text and no-browser-dialog rules.
- Rejected: turning Playwright off entirely (UI regressions would surface only in Leon's 验收).
