# Clipping (破音) is repaired automatically where that is safe

- Date: 2026-10-18
- Status: Leon's request during validation (V7): "I never cut content because of clipping. Repair it
  automatically; if a repair risks hurting the sound, don't; LACUNA decides." Supersedes the "Clipping is
  detected, not repaired" bullet of `2026-10-18-loudness-leveling.md`.
- Code: `lacuna_core/declip.py` (detection + repair), `lacuna_core/media.py` (`MediaRef.patches`,
  `SourcePool(repaired=…)`), `lacuna_core/render.py` (cache key), `lacuna_app/declip.py` (cache, attach),
  `lacuna_app/episode.py` (one line), `lacuna_app/levels.py`, `web/src/features/levels/`

## Detection (was too sensitive)
The old rule counted 3 samples in a row at |x| ≥ 0.989 as clipping. Any loud but intact peak does that: a
220 Hz tone at −0.01 dBFS gave 476 "spots" in two minutes and a voice through a limiter at 0 dBFS gave 50,
so Pei's 813 was at least partly over-counted. A side (+/−) of a recording now clips only with evidence:
- **pinned** samples: 3 in a row within 2e-5 of each other near that side's maximum (a converter out of
  range writes the same number again; a curved peak never does at speech pitches — a full-scale 60 Hz tone
  doesn't), or
- a **pile-up**: the 1.1 % band under the maximum is ≥ 4× denser than the band below it (a plateau that was
  resampled or filtered after clipping ripples, but still crowds the ceiling).
Then every run of ≥ 3 samples within 1.1 % of that ceiling is a clipped run (the old band). Measured against
the maximum of the recording itself, so a recording clipped and later turned down is found too. Runs within
0.25 s are one spot in the counts (what you hear as one 破音).

## Repair
- Least-squares AR interpolation (Janssen 1986): an order-32 model fitted (covariance method) on every clean
  stretch of 10 ms around the clipped runs; runs within 10 ms are solved together (≤ 40 ms per solve, neighbour
  runs in the window are solved too but not kept). "Consistent": a rebuilt sample is never quieter than what
  was recorded there (clipping only removes amplitude).
- **Never louder than the recording.** A rebuilt peak rises over the old ceiling; a smooth local gain dip
  (5 ms in, 50 ms out, like a limiter but only around that peak) brings it back to the ceiling. So review
  playback hears a round peak instead of a flat top or the preview soft-clipper, levels/loudness stay as
  measured, and export's master limiter has nothing extra to do. Measured on synthetic voiced speech: the
  energy above 5 kHz (where clipping's harmonics land) drops from 80–300× the unclipped speech to 1.2–1.6×.
- **Left as recorded** (LACUNA's "too risky" call): runs longer than 2 ms; a 40 ms stretch more than 40 %
  clipped; a rebuilt peak more than 9 dB over the ceiling; a rebuilt stretch the AR model predicts more than
  100× worse than the clean audio around it (the reconstruction is invented, not recovered); a solve that
  fails. Unrepaired spots are listed on 「声音」 with times to listen.

## Where it applies
- Non-destructive. Each host recording is scanned once; the repair (rebuilt samples + dip parameters,
  ~0.2 MB for 800 spots, ~4.5 MB for an hour clipped everywhere) is cached in
  `<episode>/declip/<sha1(VERSION|media_id)>.npz`. `Episode` attaches it to its `MediaRef`s (`patches`,
  never saved in state.json), and `SourcePool` overlays it on every read, so review, 整集试听, A/B clips, the
  music mix and export all hear the same repaired voice without touching `music.py` or `exporter.py`.
  `levels` measures loudness on the recording as is (`repaired=False`), so existing gains don't move.
- `Renderer.range_key` includes the repair's digest, so cached preview blocks never mix versions.
- Older episodes get it the first time they're opened: the scan runs inside `Episode()` (a 73-minute track:
  ~3 s with 800 spots, ~25 s if clipped everywhere; once). Import pays it while creating the episode.
  Bumping `lacuna_app.declip.VERSION` re-scans everything on next open. A failed scan only logs and plays
  the recording as is.

## Interface
「声音」: the 破音 card now says LACUNA repairs clipping automatically (review, listening and export hear the
repaired sound; the recording is untouched) and shows "Pei：813 处，已自动修复 810 处" per host. Only when
some spots were left as recorded does it turn amber, list their times (click = listen from 2 s before) and
suggest recording that track lower next time. No card when nothing clipped.
