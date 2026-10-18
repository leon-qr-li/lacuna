# CI: pytest and E2E run as parallel jobs; pytest uses all CPUs; E2E in two shards; main runs never cancelled

- Date: 2026-10-18
- Status: Claude 技术决策（Leon asked for a faster pipeline without losing quality）
- Supersedes / changes: — (refines the CI layout in `docs/status/foundation.md`)

**Measured before** (5 green full runs, 2026-10-18 05:25–06:24Z): wall time 5–7.5 min, always set by
Windows. Inside the one `test` job per OS everything ran back to back:
pytest 157–176 s (Windows) / 91–122 s (macOS) / 81–109 s (Linux), then E2E 109–197 s / 102–197 s / 86–126 s.
Setup (checkout, Python, uv, Node, ffmpeg, install, npm ci + build, Playwright cache) was only ~40–60 s;
queueing ~2–10 s. So the time was the two test suites in series, not installs or downloads.
Both suites are wait-bound, not CPU-bound (locally: pytest 152 s real vs 114 s CPU; E2E 145 s real vs 35 s CPU).

**Changes**
1. `pytest` and `e2e` are separate jobs per OS, so they overlap.
2. pytest runs with `-n auto` (pytest-xdist, added to the `test` extra). Locally 4 cores: 152 s → 46–52 s,
   462 passed / 6 skipped, same as serial, three runs in a row.
3. E2E runs as `--shard=1/2` and `--shard=2/2` per OS (6 jobs). Each shard starts its own three backends;
   inside a shard specs still run one at a time (`workers: 1`), in the same order. Locally: 33 + 32 = 65
   passed, 82 s and 72 s vs 145 s unsharded.
4. Concurrency: a newer push cancels an older run only on PR branches. Every push to main gets its own
   group (by commit) and is never cancelled, so each merge leaves a full result and a release no longer
   needs a manual re-run of CI.

Nothing is skipped or reduced: same 462 pytest tests and 65 E2E tests on Windows, macOS and Linux,
same build checks (tsc, i18n, brand), same install smoke job. "CI ok" still is the single merge gate and
now waits for pytest, e2e and install. The repo is public, so the extra jobs cost no Actions minutes.

**Measured after** (first full run on GitHub): push → CI ok 3 min 18 s instead of 5–7.5 min; Windows pytest 100 s
(was 157–176 s), E2E shards 102 s + 80 s in parallel. Same pass/skip counts. Table in `docs/status/ci.md`.
