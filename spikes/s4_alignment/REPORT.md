# S4 Report — EP001 raw → final alignment (how Leon edited)

_Date: 2026-10-16. Compiled by the lead from the spike agent's results; numbers come from `out/ep001_alignment.json` (`stats`, `validation`). Method and rerun steps: `README.md`._

## Validation

- **Reconstruction:** rebuilding the final's speech from the raw tracks using the map correlates with the actual final at **0.955** with one gain per segment, and **0.980** with time-varying gain.
- **Per window:** the median 1 s window correlates at 0.985. Only 9 of 3177 windows fall below 0.8.
- **Synthetic test** (`synth_test.py`, 2 runs): known random cuts were applied to the real raw tracks, then MP3-encoded.
  - 94 of 120 true per-track cut points were recovered. 93 of those are within 5 ms (median 0.1 ms); 1 is 294 ms off.
  - Where a track is audible, its source position is correct 99.8–99.9 % of the time.
  - **Misses:** two cuts less than ~0.4 s apart merge into one, and a track's offset change gets pinned to the wrong cut when that track is silent there.
  - **Not tested:** real music beds, EQ/compression/noise reduction, crossfades.
- **Resources:** peak memory 4.1 GB (within the 6 GB budget). A full rerun takes about 12–15 min on 4 vCPU.

## EP001 findings

### Duration budget

4411.9 s raw → 3684.8 s final.

- **Inserted material:** three music inserts, 153.4 s in total. None of them contains plain raw audio.
  - intro 0–41.66 s
  - interlude 2759.04–2802.84 s
  - outro 3616.83 s–end
- **Removed:** 889.1 s from Leon's track and 900.8 s from Pei's track. 745.3 s of raw is used by neither track.

### Cuts

There are **470 cut events**, about 8 per minute of final.

| Cut type | Count | Total duration |
|---|---|---|
| Under 1 s | 261 | 141 s |
| 1 s or longer | 209 | 744 s |
| Silence only (subset of the above) | 172 | 167 s |

Leon leaves a **median 0.43 s pause** at a cut. He tightens pauses; he does not remove them.

### The two tracks are edited independently (key finding)

- Pei's track is in exact relative sync with Leon's for only **114 s** of the 3346 s where both can be measured. It is more than 0.3 s off for **1809 s**.
- Forcing the tracks back into sync drops the reconstruction correlation from 0.955 to **0.55**.
- Observed behaviours:
  - He serialises crosstalk, so overlapping speech gets separated.
  - He slides interjections by 0.3–2 s (**14 cases**).
  - He removed **26** short sounds of his own under Pei's speech (9.5 s in total).

### Levels and music

- Gain: Leon ×2.23 (**+7 dB**), Pei ×1.00. This compensates for Leon's quieter mic.
- There is **no continuous music bed under speech** in this episode. Music appears only as intro, interlude and outro.

### Ambiguous regions

- Final 648–665 s: the two tracks come from raw positions 42 s apart.
- Intro around 34 s: possibly a processed Leon phrase taken from raw ≈2527 s.
- 159 unverified per-track changes that fall where that track is silent.
- 3 large backward jumps, probably alignment artifacts. This includes the earlier probe's dip near final 2910 s, which is **not** confirmed as a real reorder.

## Implications

1. **EP001 is usable as ground truth** for scoring an AI first cut, under these conditions:
   - score per track in raw time;
   - be lenient for cut positions inside pauses;
   - be lenient for changes on a track that is silent at that moment.
2. **Per-track timing editing is central to Leon's style, not an edge case.** The edit model and the renderer must support:
   - independent per-track slips;
   - serialising overlaps;
   - removing short sounds on one track only.

   A mono, transcript-only cutter cannot reproduce this.
3. **Pause handling:** shorten pauses toward roughly 0.4 s rather than deleting them. This matches "preserve the conversation".
4. **Default gain:** per-track loudness matching is a baseline step (Leon's track needed about +7 dB).
5. **Sound design:** music at structural points (intro, interlude, outro) is the observed default for this series. Underscore under speech is not observed in EP001.
