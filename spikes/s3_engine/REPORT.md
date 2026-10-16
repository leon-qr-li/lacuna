# S3 Report — per-track non-destructive edit engine

_Date: 2026-10-16. Gate 2 (`docs/handoff/05_TECHNICAL_FEASIBILITY.md`), per D31. Condensed by the lead from the spike agent's report; numbers in `out/results.json` and `out/previews.json`._

## Summary

`lacuna_core/` is about 1,190 lines of Python using numpy and soundfile; ffmpeg is used only to import foreign media. It provides:

- **Edit list (EDL):** clips per track that point at source audio ranges, identified by sha256. Every change is an op:

  | Op | What it does |
  |---|---|
  | `CutRange` | Ripple cut on all tracks or on one track |
  | `LiftRange` | Delete on one track only |
  | `SlipRegion` | Move one track's material in time |
  | `TrimClip` | Trim a clip |
  | `InsertClip` | Insert a clip |
  | `SetTrackGain`, `SetClipGain` | Gain |
  | `SetFades` | Fades |
  | `AddDuck` | Ducking |
  | `SetRoomTone` | Room-tone fill |

  - The log is append-only, with undo/redo, `at_version`, and JSON round-trip.
  - **No op can create samples.**
- **Renderer:** streaming and sample-exact. Every real seam gets a 16 ms crossfade: equal-power between different material, equal-gain where only the gain changes. Optional equal-power room-tone fill and a soft-clip guard. Chunked output is bit-identical to a one-shot render, and every render is deterministic.
- **`refine.snap_cut`:** moves a cut point to the joint energy valley across tracks within ±150 ms, then to a zero crossing.
- **`preview.Previewer`:** ±10 s and A/B renders on a 2 s block grid. The cache key hashes exactly the plan parts that affect each block.
- **`seams.check_seams`:** click detector requiring both a delta ratio and a high-frequency (HF) ratio.

## Proof on Leon's real edit (EP001)

The S4 map was converted into an EDL: 495 clips per track, 174 single-track lifts, Leon +6.97 dB. The render was compared with the published final.

| | 4-min window | Full episode (3617 s) |
|---|---|---|
| Lag vs final | 1 sample | n/a |
| NCC, 100–3800 Hz | **0.946** | **0.951** |
| 1 s window NCC, p10 / p50 / p90 | 0.906 / 0.984 / 0.997 | 0.898 / 0.977 / 0.996 |
| Same window without single-track lifts | 0.925 | n/a |

Removing the single-track lifts lowers the score, which is direct evidence for D31. The remaining gap comes from Leon's EQ, compression and noise reduction, plus the limits of the S4 map. It is not caused by the renderer.

## Performance

| Measure | Result |
|---|---|
| Full-episode render | 17.7 s (**204× real time**) |
| Peak RSS | 123 MB, flat during the render |
| ±10 s preview, cold | median 0.061 s, max 0.092 s |
| ±10 s preview, warm | 0.002 s |
| After a local edit | 0.043 s |
| A/B pair | about 0.09 s (target was < 3 s) |
| Seams, 16 ms crossfade | **0 clicks** in 124 real seams |
| Same seams as hard cuts | 63 flagged |

## Listening pairs

Located in `/mnt/project-files/lacuna/previews/`, with a Chinese README:

- `01_pause_tighten`: a 1.14 s pause tightened to 0.36 s.
- `02_interjection_slip`: Pei's 嗯 slid +1.36 s on her track only, with room-tone fill.
- `03_single_track_delete`: one of Leon's real single-track removals.

All three pairs: 0 clicks, about 0.04 s to render.

## Tests

`python3 -m pytest -q tests` → **38 passed** in about 4 s (re-run by the lead, 2026-10-16).

Coverage: EDL ops, undo and validation; exact placement; chunked = one-shot; crossfade; per-track independence; room tone; ducking; pan; snapping; cache soundness (randomized); and an EP001 integration test, which is skipped when the raw audio is absent.

## Limitations and next steps

1. **No mastering stage yet.** With Leon at +7 dB the mix peaks around +7.6 dBFS, and the soft clip touched 0.1 % of samples. The export stage needs a leveller/compressor plus LUFS and true-peak normalisation.
2. **Track buses are mono.** Stereo music needs a 2-channel bus.
3. **Sample-rate conversion happens only at import** (`media.conform`).
4. **The preview cache is in memory only.** Still missing: a disk tier and a crash-safe project store.
5. **The click detector is heuristic.** Breath and room-tone continuity are not scored.
6. **Cut refinement uses energy only.** It should also treat ASR token boundaries as hard constraints.
7. **A slip overwrites its destination.** The editorial layer must check that only silence or room tone is overwritten.
8. **Not yet measured on Windows or macOS.** The code is pure Python plus libsndfile.

## Rerun

```bash
python3 -m pytest -q tests
python3 spikes/s3_engine/run_proof.py --scratch /some/scratch   # about 2.5 min
python3 spikes/s3_engine/make_previews.py --out /mnt/project-files/lacuna/previews
```
