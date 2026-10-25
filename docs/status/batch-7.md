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

## Next action
Read Leon's picks (`ArtifactData list choices` on the URL above), then implement them in one batch
on this branch (unless he picked otherwise in `plan`), with tests, then code freeze.
