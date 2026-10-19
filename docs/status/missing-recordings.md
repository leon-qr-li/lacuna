# Missing recordings (声音放不了, 2026-10-19)

State: fix built (decision `missing-recordings`); PR with the `staging` label.
- Root cause: PULSE-013's raw tracks stayed on Leon's PC (`C:\Users\liqin\Downloads\`), the desktop
  move (#127) brought only the workspace. sha256 of both files on his PC == the episode's media ids.
- Next: after merge, upload the two files on the real site (banner on the PULSE-013 page) so the
  recordings live in `/data/workspace/episodes/PULSE-013/media/`; staging picks them up on its next copy.
- Tests: `tests/app/test_missing_sources.py`, `web/e2e/missing_sources.spec.ts`.

Update 22:10Z: #138 merged and live on production. Leon then chose a full clean-out instead of
re-uploading (decision `cloud-clean-out`): PR adds `lacuna_app/clear_once.py` (runs once at startup on
the cloud). Next: staging clears → merge → production clears → Leon tests end to end → remove clear_once.

Update 22:30Z: #140 ran on staging and production (Leon: episode list empty). clear_once removed;
the restart also clears the stale 生化危机 row in 导入任务 (in-memory importer job). Done; Leon testing E2E.
