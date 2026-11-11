# Batch 10: third scan + load test (code freeze)

Thread 「第十批：再扫一遍加压力测试」 (Leon 2026-10-26: scan again and load test with k6, without spending
money). Nothing was sent to the live site: no AI calls, mail, ASR, R2 or extra traffic.

## Scan
pytest 887 passed / 17 skipped; `npm run build`; E2E 153 / 153 on CI (PR #225). No UI text changed this batch.

## Load test (`scripts/loadtest/`, README there)
A local cloud-mode server (`LACUNA_CLOUD=1`, `LACUNA_ACCESS=off`, mock editor) in the 4-core / 15 GB cloud
container; 151 people, each with a show holding one 60-minute two-track 44.1 kHz episode (480 AI edits), 5
shows shared. k6 ran on the same machine (report page https://claude.ai/artifact/H9di5iTLanzvMCh1fBZmdg). Each virtual user opens the site and an episode, beats presence every
5 s, reviews edits (audio fetched again from the playhead, 2 MB ≈ 24 s), listens to A/B clips, reads the
transcript window; 3 more watch the import list.

| Run | Pace | Comfortable (p95 review < 0.25 s, audio < 2 s) | Breaks down |
|---|---|---|---|
| ramp (before fix) | review every ~15 s | 40 | 60: audio p95 16 s |
| ramp2 (after fix) | review every ~15 s | 40 | 60 |
| real | review every ~45 s, A/B every ~90 s | 60-80 | 100: audio p95 21 s, opening the site 20 s |
| idle | page open, presence only | 300 (16 % of a core) | not reached |

No failed request in any run (after the keep-alive fix). The server process never used more than ~1.45 cores:
one Python process, rendering audio under the GIL, is the ceiling; the 40-thread pool fills first and then
static files and the bundle wait too.

Memory: before the fix 11.7 GB at 150 people (7.8 GB at 100; the container has 7 GB) and nothing freed when
they left. After: 5.7 GB at 150, ~4.2 GB at 100. What is left is ~40 MB per show opened since the last restart
(the show's app, its 3 open episodes, 24 A/B clips each) plus the shared 1 GB cache.

## Fixes (PR #225, deployed)
1. uvicorn's 5 s keep-alive vs cloudflared's 90 s: a request sent as an idle connection closed met a reset
   (→ 502). Now 120 s (`lacuna_app/__main__.py KEEP_ALIVE`).
2. Listening caches: one 1 GB budget for all episodes and music previews (`lacuna_core.preview.SharedBudget`,
   `episode.PREVIEW_BUDGET`).

## Not done / later (not bugs for the freeze)
- Show apps are never let go before a restart (~40 MB each): fine for beta; before ~100 active shows between
  deploys, free shows idle for an hour.
- Audio rendering in the web process: moving it to a worker process (or several) lifts the ~1.45-core ceiling.
- Not measured here: Cloudflare (Access / tunnel), real imports and exports running at the same time (they
  use all 4 cores for minutes, see `perf.md`), uploads, the real DO server (Intel 4 vCPU, 8 GB, staging on the same box).
