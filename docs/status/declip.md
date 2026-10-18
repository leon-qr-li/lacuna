# Automatic clipping repair (验收 V7) - 2026-10-18

State: merged (PR #115), waiting for the batched release; covered by the second full scan (`docs/status/sweep-2.md`).

- Decision: docs/decisions/2026-10-18-auto-declip.md (detection, repair, safety limits, where it applies).
- Core: `lacuna_core/declip.py` (`scan` → `Patches` + `Report`), `MediaRef.patches` + `SourcePool(repaired=)`
  in `media.py`, repair digest in `Renderer.range_key`.
- App: `lacuna_app/declip.py` (cache in `<episode>/declip/*.npz`, `attach`, `track_report`), one line in
  `Episode.__init__`; `levels.py` drops its own clip detection, measures raw (`repaired=False`) and reports
  `clip_count` / `clip_repaired` / `clip_kept` / `clip_times` (kept spots only) from the repair.
- Web: 「声音」 破音 card (`web/src/features/levels/`).
- Tests: `tests/test_declip.py` (quality on clipped synthetic speech, clean / full-scale tones untouched,
  long runs left alone, resampled plateaus, chunking, pool + cache key), `tests/app/test_declip.py`
  (episode playback / mix use the repair, recording bytes unchanged, older episode repaired on open then
  cached, failure never blocks opening, version bump re-scans, 声音 counts), `tests/app/test_levels.py`,
  `web/e2e/levels.spec.ts`.
- Not verified on Leon's real Pei track (audio stays on his PC). After the batched update, 「声音」 on EP001
  shows the real counts; the sweep should look at them (expect far fewer than 813 if the old count was
  inflated by loud intact peaks).
- Started from the hand-over branch `v7-declip` (a2236eb) of the validation thread: kept its "pinned run"
  idea for detection and its measured examples; replaced the repair (covariance AR, joint solves, residual
  guard, never-louder dips), and attached the repair to the media refs instead of editing the music/export pools.
