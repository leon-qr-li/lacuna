# Batch 7: visual walkthrough + copy sweep

Thread 「第七批：视觉走查与文案整理」. Last development batch before the code freeze.

## State (2026-10-25)
- Leon's instruction: walk through and sweep only, **no product code changes**; every question goes
  into one click-to-choose decisions page. Built and published (private Artifact, choices saved in its
  `choices` db collection): https://claude.ai/artifact/Q7kCPtogpamxffd7ZSoJTK
- Covered: every main-site page (dark/light × zh/en, local cloud-mode server), widths 1280/1024/390,
  admin (demo data), new-user flow + 49-step sample tour, error/offline/loading/dialog/export/
  session-expired/chat states, all 2257 web strings + 662 server strings (`tr()` incl. emails).
- Decisions page holds: 1 rollout question, 26 objective fixes (B1–B26), 11 visual choices (T1–T11),
  12 terminology choices (W1–W12), 38 copy rows (zh/en before→after), the speed-test method (S1).
- Server ↔ R2 speed: **not measured**. Prod has no shell reachable from Claude and this container
  has no bucket credentials. Options are in S1 (recommended: an owner-only admin 「测速」 button).

## Implementation (2026-10-25, after Leon's picks)
Leon picked every recommended option (one PR). Done on this branch: all of W1–W12, the 38 copy rows,
B1–B26, T1–T11 and S1; the record is decision `2026-10-25-copy-sweep`. New pieces: `features/states`
(error / empty states), `features/mobile` (phone menu), `lacuna_app/speedtest.py` (+ admin `测速`),
`tests/app/test_batch7.py`, `web/e2e/batch7.spec.ts`. Leon's rule for copy changes: every changed screen is
screenshot in zh/en, dark/light, 1440 / 1024 / 390 and checked for overflow before shipping.

## Next action
CI green → squash merge → prod, then code freeze (full regression, Leon's week of testing).
