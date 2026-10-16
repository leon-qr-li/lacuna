# Spike S5 — AI first cut "like Leon" (input package + scorer)

Tests whether Claude can make a first cut from **text + numeric acoustic features only** (no audio
to the API), scored against Leon's real EP001 edit (S4 ground truth).

## Files

| File | What |
|---|---|
| `build_input.py` | Builds the editor input package from the two raw tracks + ASR. **Never reads S4 ground truth.** |
| `out/asr/` | Full-track Paraformer + SenseVoice outputs (S2 schema, per-track Silero VAD; produced by `spikes/s2_asr/run_paraformer.py` / `run_sensevoice.py` on the full 16 kHz tracks during S2 — same scripts and settings, copied here). |
| `out/ep001_tokens.json` | Per-track tokens: stable id (`L000123` / `P000045`), text, energy-refined start/end (raw s), pause_after, Paraformer-vs-SenseVoice disagreement flag with SenseVoice reading. |
| `out/ep001_features.json` | Per-utterance features (rate, normalized energy, F0 median/range, end contour, pause before/after, SenseVoice event/emotion), overlaps (who started first, ids, text), floor gaps, long silences, non-speech sound candidates, per-track stats. |
| `out/ep001_editor_input.md` | The LLM-readable episode document (format documented at its top). ~149k characters, ~80k tokens (estimate). |
| `edit_ops.schema.json` | JSON Schema of the edit ops the editor must output (`cut`, `tighten_pause`, `slip`, `keep_flag`; token ids or raw seconds; reason / confidence / category). |
| `editor_brief.txt` | Editor instructions — a summary of the Editorial Playbook only (no S4 numbers). |
| `score.py` | Scorer: AI ops vs S4 ground truth, per track in raw time. |
| `make_sanity_ops.py` | Builds `out/sanity/oracle_ops.json` (ops from ground truth) and `baseline_ops.json` (tighten every floor pause > 0.8 s to 0.4 s). |
| `out/sanity/*_score.{txt,json}` | Scores of the two sanity inputs. |

## Rerun

```bash
S2=<scratch dir with venv + 16 kHz full tracks, see spikes/s2_asr/README.md>
$S2/venv/bin/python -I build_input.py --leon-wav $S2/audio/Leon_full.wav --pei-wav $S2/audio/Pei_full.wav \
    --asr-dir out/asr --out-dir out                    # ~45 s
python3 make_sanity_ops.py
python3 score.py --ops out/sanity/baseline_ops.json --json out/sanity/baseline_score.json
python3 score.py --ops <ai_ops.json>                   # score an AI first cut (numpy only)
```

## Scoring rules (summary; details in `score.py` docstring)

- Ground-truth removed = S4 `removed_raw` per track ∪ verified muted spans; unverified muted spans are
  "ambiguous" and never penalised.
- Speech frames (inside a token span): ±0.10 s tolerance. Pause frames: position-free, matched amount
  per pause = min(AI, Leon) — covers S4's "lenient inside pauses / where a track is silent".
- Event level: removal runs matched within ±0.30 s, or (pause-only events) anywhere in the same pause.
- False deletion (high severity) = AI removed speech that Leon kept (outside tolerance), listed with text.
- Final duration is estimated as raw − mean(per-track removed) for both AI and Leon (formula error on
  Leon's own edit: 3517 s vs actual 3531 s from raw; music inserts excluded).
- Interjection agreement uses a listener-centric definition: a short phrase is "moved" by Leon if its
  placement relative to the other host changed by 0.3–3 s. That counts 165 of 345 candidates — far
  more than the ~14 deliberate slides in the S4 REPORT, because independent per-track cuts also shift
  placement. AI-side placement only counts explicit `slip` ops (AI cuts that desync are not modelled).
