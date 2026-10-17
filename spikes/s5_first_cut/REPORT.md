# S5 Report: AI first cut v1 (blind) vs Leon's real EP001 edit

_2026-10-17._

## Setup

| Item | Detail |
|---|---|
| Editor | A Claude agent working blind. It saw only `editor_brief.txt`, the schema, `out/ep001_editor_input.md` (about 80k tokens of verbatim transcript plus acoustic features) and the Editorial Playbook. It never saw the final mix or the S4 data. |
| Output | `out/ai_first_cut_ops.json`: 438 ops, schema-valid |
| Scoring | `score.py` against the S4 ground truth, per track, in raw time |
| Full scores | `out/ai_first_cut_score.json` |

## Results

| | Leon track (L) | Pei track (P) |
|---|---|---|
| Removed time: AI vs Leon | 272 s vs 899 s | 243 s vs 902 s |
| Precision / recall, seconds | 0.70 / 0.21 | 0.63 / 0.17 |
| Precision / recall, events | 0.81 / 0.41 | 0.62 / 0.51 |
| Speech removed: AI vs Leon | 93 s vs **441 s** | 76 s vs **63 s** |
| Speech precision / recall | 0.71 / 0.15 | 0.26 / 0.28 |
| False deletions (speech Leon kept) | 26.8 s (60 spans) | **56.8 s** (107 spans) |
| Missed speech removals | **374.9 s** | 45.3 s |

| Overall | AI | Leon | Baseline |
|---|---|---|---|
| Estimated final length | 4155 s (69 min) | 3517 s (58.6 min; actual speech 3531 s) | 4106 s |
| Median floor pause | 0.57 s (raw 0.57) | 0.39 s | 0.41 s |
| Pauses longer than 1 s (raw: 220) | 72 | 81 | 0 |

The baseline is the trivial rule "tighten every pause to 0.4 s". It gets **higher pause recall than the AI** (L 0.43 vs 0.26).

**Interjection moves.** Leon re-placed 165 of 345 short phrases (broad definition, which includes the side effect of per-track cuts). The AI moved 1.

## Diagnosis

The AI's taste points the right way: what it cuts on Leon's track mostly matches what Leon cut (event precision 0.81). But it is **badly mis-calibrated** in four ways.

1. **The pause target is wrong.**
   - The AI tightened only gaps of 1.2 s or more, and only down to 0.7–0.8 s.
   - Leon tightens almost every pause to about 0.4 s.
   - Fix: make this a learned rule. It is pure calibration.
2. **Leon is far harder on his own speech than on Pei's.**
   - He removed 441 s of his own speech but only 63 s of Pei's.
   - The AI's biggest misses are multi-second stretches of Leon rambling or repeating himself. Examples: 786.8 s "我们就到那儿直接就干…", 4370.7 s "那么nintendo…元宇宙吧", 274.9 s "…四大联盟竟然是我从来没看过的运动".
   - The Playbook's "when uncertain, keep" made the AI refuse these content trims.
3. **Pei's speech should be protected more.**
   - The AI cut Pei's disfluencies at about the same rate as Leon's.
   - Leon mostly kept Pei's, so 57 s of false deletions land on her track.
   - Most of them are short fragments such as "呃就是" and "对这也就就".
4. **Per-track timing work is almost absent.** One slip, against Leon's pervasive re-placement. This needs examples and probably a dedicated pass.

Whether the "false deletions" sound bad is not established. They are speech Leon kept, and the AI's version may still sound fine. Only listening can tell. Missed removals matter more for the 1–2 h review target, because each one costs Leon a manual edit.

## Conclusion

- **v1 is not "like Leon" yet.** It would give a 69-min episode where Leon made 59, and it would leave most of his self-trims undone.
- The errors are **systematic and learnable**:
  - pause target;
  - an asymmetric host policy (own speech vs co-host's speech);
  - content trims of the host's own rambling;
  - per-track re-placement.
- This supports making the learning module core (D27).

## Next: v2 calibrated, with held-out evaluation

1. Split EP001 into a calibration half (raw 0–2200 s) and a held-out half (2200–4412 s).
2. From the calibration half only, derive explicit rules and examples:
   - pause targets;
   - per-host removal rates and the kinds of speech removed;
   - content-trim examples;
   - per-track re-placement examples.
3. Give these to the editor as learned rules.
4. Score only on the held-out half.

This is the honest test of whether learning from one episode transfers.

## v2 results: learned rules, blind edit on held-out half (2026-10-17)

The rules came from raw 0–2200 s only (`learned_rules_calib.txt`). The blind edit covers raw 2200 s to the end, and it was scored with `score.py --min-raw 2200`. Ops: `out/ai_v2_heldout_ops.json` (384 ops). Scores: `out/ai_v2_heldout_score.json` and `out/ai_v1_heldout_score.json`.

**How much is removed**

| | v1 | v2 | Leon | 0.4 s baseline |
|---|---|---|---|---|
| Estimated final length (s) | 2072 | **1830** | 1806 | 2049 |
| Speech removed, L / P (s) | 45 / 52 | 179 / 34 | 176 / 41 | 0 / 0 |
| Median floor pause (s) | 0.55 | 0.41 | 0.39 | 0.40 |
| Pauses longer than 1 s that remain | 38 | 2 | 41 | 0 |

**How well it matches Leon's cuts**

| | v1 | v2 | 0.4 s baseline |
|---|---|---|---|
| Recall by seconds, L / P | 0.23 / 0.21 | **0.50 / 0.56** | 0.26 / 0.30 |
| Recall by events, L / P | 0.41 / 0.56 | **0.71 / 0.79** | 0.46 / 0.60 |
| Speech precision, L | 0.69 | 0.46 | – |
| False deletions, L / P (s) | 14 / 39 | 96 / 29 | 0 / 0 |
| Missed removals, L / P (s) | 146 / 28 | 100 / 35 | 176 / 41 |

**Diagnosis**

1. **Calibration transfers.**
   - v2 removes about as much as Leon does, its median pause matches his, and Pei stays protected.
   - Recall roughly doubles compared with v1.
2. **Content-trim selection is the weak point.**
   - Precision on content trims is 0.44: v2 cut different tangents from the ones Leon cut.
   - This is taste. The next step should be a review loop, not more rules: rank content trims for Leon to approve, and learn from his restores (D27).
3. **Pause shaping is too uniform.**
   - Leon keeps some long pauses (41 longer than 1 s).
   - Treat these as dramatic or turn-taking pauses and keep them.
4. **Interjection moves cannot be learned as slips.**
   - They mostly follow from asymmetric per-track pause cuts.
   - Model them that way instead.
