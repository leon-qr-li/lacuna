# Missing recordings (声音放不了, 2026-10-19)

State: fix built (decision `missing-recordings`); PR with the `staging` label.
- Root cause: PULSE-013's raw tracks stayed on Leon's PC (`C:\Users\liqin\Downloads\`), the desktop
  move (#127) brought only the workspace. sha256 of both files on his PC == the episode's media ids.
- Next: after merge, upload the two files on the real site (banner on the PULSE-013 page) so the
  recordings live in `/data/workspace/episodes/PULSE-013/media/`; staging picks them up on its next copy.
- Tests: `tests/app/test_missing_sources.py`, `web/e2e/missing_sources.spec.ts`.
