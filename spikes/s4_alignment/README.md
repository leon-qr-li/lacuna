# Spike S4 — raw/final alignment (reconstructing a manual edit)

Recovers, from audio alone, how an episode was edited: which raw span of each host track
appears where in the final mix, which raw spans were removed, where non-raw material
(music / clips) was inserted, and where the two host tracks were edited differently.
Findings for EP001 are in `REPORT.md`; the machine-readable map is
`out/ep001_alignment.json` (numbers only, no audio).

## Files

| File | What |
|---|---|
| `align.py` | The aligner. Raw tracks + final in, JSON out. |
| `synth_test.py` | Ground-truth test: builds a fake "final" from a slice of the raw tracks with a known edit list, MP3-encodes it, runs `align.py`, scores the result. |
| `out/ep001_alignment.json` | EP001 result. |
| `REPORT.md` | EP001 findings, precision evidence, limits. |

## Rerun

```bash
# EP001 (about 10-15 min on 4 cores; peak RAM ~2.5 GB)
python3 -I align.py \
  --leon  "/path/原始双轨_Leon.wav" --pei "/path/原始双轨_Pei.wav" \
  --final "/path/最终成品.mp3" \
  --out out/ep001_alignment.json --cache-dir /some/scratch/dir

# re-run only the analysis stage from cached Viterbi paths (seconds)
python3 -I align.py ... --analyse-only [--no-insert-probe]

# synthetic ground-truth test (about 3-4 min)
python3 -I synth_test.py --leon ... --pei ... --work /some/scratch/synth --cache-dir /some/scratch/cache_syn
```

Needs `ffmpeg` on PATH, Python 3.10+, numpy, scipy, soundfile (synth test only).
Inputs are only read. The cache dir holds 8 kHz float32 decodes (~400 MB for a 74-min
episode) and intermediate anchors/paths; keep it outside the repo (it contains audio).
Use a separate `--cache-dir` per final file when running several at once.

## Method

Model: `final(t) ≈ gL(t)·Leon(t + oL(t)) + gP(t)·Pei(t + oP(t)) + other(t)`, with the
per-track offsets `oL`, `oP` (raw time − final time) piecewise constant. Everything runs on
the waveform at 8 kHz (speech band survives MP3 encoding and Leon's processing well:
matched 1 s windows correlate at 0.95–0.99).

1. **Mix anchors** – 1 s windows of the final every 0.5 s; NCC search in Leon+Pei, first at
   the previous offset (±10 ms), then a local window (−30 s…+150 s), then a 2 kHz decimated
   global search (re-checked at 8 kHz). Gives the coarse offset curve and catches moves.
2. **Per-track anchors** – 0.5 s windows every 0.25 s searched in each track alone within
   ±6 s of nearby mix offsets. This is what exposed that the two tracks are usually *not*
   in sync in the final (see REPORT).
3. **Joint Viterbi over (oL, oP) pairs** on 10 ms frames. Candidate offsets = all anchor
   offsets (shared by both tracks) seen within ±12 s. Emission = 1 − fraction of final energy
   explained by a joint two-regressor least-squares fit (Leon@oL, Pei@oP) over 150 ms; the
   cross term absorbs mic bleed so a silent track cannot "borrow" the other host's bleed.
   Transitions: joint cut (both tracks jump by the same amount) λ=3; one track only λ=8;
   both tracks on the same frame by different amounts λ=9.
4. **Discovery pass** – loud spans the path cannot explain are re-searched with short
   queries (found nothing extra on EP001).
5. **Boundary refinement** – each switch is placed at the sample that minimises the summed
   squared error of the two hypotheses within ±250 ms (other track subtracted). Two
   uncertainty measures are reported: `ambiguity` (10 ms frames around the switch where the
   two hypotheses are indistinguishable) and `heard_bounds` (last frame the switching track
   is clearly heard at the old offset → first frame at the new one; wide when a track is
   silent around its own edit).
6. **Inserts** – ≥1 s spans where the raw tracks explain <5 % of the final's energy; each is
   probed with a global search for re-used raw material.
7. **Outputs** – segments (constant (oL, oP) spans) with source spans, gains, per-track
   evidence and confidence; edit events (joint / single-track / asym cuts and backward
   jumps); removed raw spans per track and from both tracks; inter-track offset (desync)
   runs; "muted" spans (raw track has speech at its mapped position but is not heard);
   validation by reconstruction.

## JSON conventions

Times in seconds. `offset = raw − final`. `*_src = [raw_start, raw_end]`. `jump_s` = offset
change at an event = raw seconds skipped (>0) or re-used (<0). `evidence_s` = seconds in
which that track is clearly heard (explained energy > 0.5). `track_confidence: inferred` =
the track is silent there, its offset is carried by continuity and cannot be verified.

## Known limits

* A track that is silent (clean or gated mic) around its own edit carries no information
  about where exactly that edit is; only the amount is known. 
* Pause material between two cuts is unverifiable at sub-pause resolution.
* The decomposition of simultaneous per-track changes into "joint + single" vs "asym" depends
  on the λ priors; totals per track do not.
* Gains are a single LS gain per track per window; EQ/compression/noise reduction show up
  as residual, not as parameters.
