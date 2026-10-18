# Automatic clipping repair (破音) - 2026-10-18

State: branch `v7-declip`, committed locally, not pushed / no PR yet (coordinator merges).

- Detector rewritten (`lacuna_core/declip.py` `find_runs`): flat runs (>= 3 equal samples) at >= 95 % of the
  recording's own peak. Clean loud tones / limited speech no longer count (old rule: 476 / 12 spots in 2 min).
- Repair: short runs (<= 2 ms) restored by constrained AR interpolation; long, over-1.5x and densely clipped
  runs left alone. `scan` streams the file (two passes, 1 M-sample blocks with overlap).
- Applied non-destructively via `SourcePool(repairs=…)`; `lacuna_app/declip.py` scans each host recording once
  and caches it in `<episode>/declip/`. Used by: review previewer (`episode.py`), music mix + music player
  (`music.py`), export (`exporter.py`), level measurement (`levels.py`). Playback never blocks on a first scan.
- 「声音」: the clipping card (times + "only marks, go cut it") is replaced by one line per host
  (`levels-declip`): repaired N, left M. API fields `clip_count` / `clip_times` → `clip_fixed` / `clip_left`.
  `levels.json` entries re-measure automatically (declip VERSION is in the track key).
- Tests: `tests/test_declip.py` (detector, repair quality, long runs untouched, chunking, render/export path,
  overhead), `tests/app/test_declip.py` (playback/music/export use it, cache, background scan, source untouched),
  `tests/app/test_levels.py` (counts on the current cut), `web/e2e/levels.spec.ts`.
- Decision: docs/decisions/2026-10-18-auto-declip.md

Open / next
- Not validated on Leon's real Pei track (no access here). Worth checking how many spots the new detector
  finds there and listening to two or three repaired ones. If the recordings are MP3/AAC or were resampled
  after clipping, flat tops are no longer flat and nothing is detected (by design: nothing safe to repair).
- Tuning knobs, all in `lacuna_core/declip.py`: `MAX_RUN_S`, `CAP`, `MAX_DENSITY`, `FLAT_TOL`; bump `VERSION`
  after changing any of them so cached repairs and level measurements are redone.
