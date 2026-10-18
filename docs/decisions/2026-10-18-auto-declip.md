# Clipping (破音) is repaired automatically where that is safe; the list of times goes

- Date: 2026-10-18
- Status: Leon's request (2026-10-18): "I never cut content because of clipping; repair what can be repaired
  safely, leave the rest; LACUNA decides." Supersedes the "Clipping is detected, not repaired" bullet of
  `2026-10-18-loudness-leveling.md`.
- Code: `lacuna_core/declip.py`, `lacuna_app/declip.py`, `lacuna_core/media.py` (`SourcePool(repairs=…)`),
  `lacuna_app/levels.py`, `web/src/features/levels/`

## Detection
The old rule (3 samples in a row at |x| >= 0.989) counted every loud but intact peak: a 220 Hz tone at
-0.01 dBFS gave 476 "spots" in 2 minutes, a limiter hugging 0 dBFS 12, which is how Pei's 40-minute track
reached 813. A clipped run is now **>= 3 consecutive samples pinned at one value** (same sign, each within
2e-5 relative of its neighbour) **at >= 95 % of that recording's own peak**. An intact peak is curved (a
100 Hz sine at full scale changes by ~9e-5 between its top samples), a converter that ran out of range writes
the same number again. "Own peak" also catches a recording that clipped and was turned down afterwards.
Runs that start within 0.25 s of each other are one spot (what you hear as one 破音).

## Repair
- Only short runs (<= 2 ms, 96 samples at 48 kHz). The flat top is replaced by least-squares AR
  interpolation (Janssen; order 16, 12.5 ms of context each side, re-estimated 3x), constrained so no
  restored sample is below the clip level ("consistent" declipping).
- Left alone (counted as "not repaired"): longer runs; runs whose restored top would exceed 1.5x the clip
  level; runs in a passage where more than 20 % of the context is itself clipped (heavy overload: the model
  would only learn the flat tops). A wrong guess sounds worse than the flat top, so in doubt LACUNA leaves it.
- Synthetic speech clipped by 2 dB: squared error on the repaired samples is ~2 % of the clipped signal's;
  clipped by 6 dB: 56 of 227 spots repaired, 171 left alone.

## Where it applies
- Non-destructive: the recordings are never written. Each host recording is scanned once; the patches
  (positions + restored samples, ~0.7 MB for a heavily clipped 40-minute track) are cached in
  `<episode>/declip/v<VERSION>_<hash>.npz` and in memory, and `SourcePool` applies them as it reads. All
  renders (review, 整集试听, music mix, A/B clips, export) therefore hear the same repaired voice; analysis
  (ASR, AI cut, room tone, music import) still reads the raw files.
- Restored peaks exceed 0 dBFS; the render path is float, so export carries them to the master's true-peak
  limiter (the export renderer has no soft clipper) and preview to its soft clipper.
- Playback never waits for a first scan: it starts unrepaired and the repairs join the pool when the
  background scan finishes (`repair_key` is part of the segment-cache key, so blocks rendered before are not
  reused). Export and the 「声音」 measurement wait for the scan. Import runs it as part of levelling.
- Cost, once per recording: two reads of the file plus ~0.6 ms per clipped run (40-minute 24-bit track: clean
  5.4 s, lightly clipped 6.2 s, clipped everywhere ~19 s). Playback overhead is within measurement noise
  (120 s rendered in 2 s blocks: 156 ms plain vs 149 ms repaired).

## Interface
「声音」 no longer lists times. Under the volume card one muted line per affected host:
"Pei：LACUNA 已自动修好 12 处短促破音。2 处较长的破音没有修（修了反而失真）。" No line when nothing clipped.
Counts are on the current cut (cut-away spots are not counted).
