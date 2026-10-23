# CI speed (2026-10-18)

**2026-10-23: Linux only.** Windows and macOS removed from the matrix; Playwright retries a failed test
once in CI (decision `docs/decisions/2026-10-23-ci-linux-only.md`). Jobs now: `pytest`, `e2e 1/2`,
`e2e 2/2`, `CI ok`. The per-OS notes below are history.

Decision: `docs/decisions/2026-10-18-ci-speedup.md`. Workflow: `.github/workflows/ci.yml`.

Jobs per OS (windows / macos / ubuntu): `pytest <os>` (only when Python changed, `-n auto`),
`e2e <os> 1/2` and `e2e <os> 2/2` (Python or web changed), `install <os>` (installer / pyproject changed).
"CI ok" is the merge gate.

Measured on GitHub (full run: Python + web + install all triggered).

| | before (5 runs, 2026-10-18 05:25–06:24Z) | after (PR #102 run 39105408909) |
|---|---|---|
| wall time, push → CI ok | 5 min 0 s – 7 min 30 s | **3 min 18 s** |
| Windows pytest | 157–176 s | 100 s (461 passed, 7 skipped: same) |
| macOS / Linux pytest | 91–122 s / 81–109 s | 62 s / 59 s |
| Windows E2E | 109–197 s (65 tests, after pytest) | 102 s + 80 s shards (33 + 32 = 65), in parallel |
| slowest job | Windows test 333–441 s | Windows E2E 1/2 180 s (≈70 s of it setup) |

Remaining time is mostly per-job setup on Windows (~70 s: checkout, Python, uv, Node, ffmpeg, npm ci + build,
Playwright cache restore) and each shard's three backends starting (~20 s).

Open: if a shard becomes much slower than the other as specs are added, rebalance (Playwright shards by file).
