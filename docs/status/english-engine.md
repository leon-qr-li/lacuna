# English engine (future direction 3)

Thread 「英文剪辑引擎」. Decision: `docs/decisions/2026-10-19-english-engine.md`. Starting point: the
measurement report `/mnt/project-files/lacuna/docs/英文剪辑实测_2026-10-19.md`.

## Done (PR 1: English works end to end)
- Language per show (节目设置 → 节目语言) and per import (导入新一集 → 这一集说的语言).
- `asr.ENGINES`: zh = Paraformer + SenseVoice(zh); en = Parakeet-TDT 0.6B v2 + SenseVoice(en). Pieces merged
  into words; models downloaded per language on first use.
- Features: English format notes in the editor document, case/punctuation-insensitive cross-check.
- First cut: English brief + defaults for English episodes.
- Spaces between English words everywhere text is joined (`words.py`, `web/src/words.ts`).
- Measured in the cloud container (4 vCPU): 5 min of English audio imported in 45 s including model load
  (ASR ~37 s), real importer, rule first cut (no API key in the container).
- Tests: `tests/app/test_english.py`; real models `tests/test_asr_en_real.py` (set `LACUNA_ASR_MODELS`).

## Dropped um/uh (spike + first version, same PR)
- Problem: English recognisers drop most fillers (Whisper all; Parakeet wrote 34 in 30 min of a CC-BY
  podcast, SenseVoice 1), so the AI cannot cut what it cannot see.
- Spike (scripts in the thread's scratch; data: Request for Explanation ep4 + ep6, 15 min each, mono mix):
  every short sound with no word (energy activity ≥0.15 s, ≥50 ms from any word) is decoded again on its
  own by Parakeet. Result: 28 extra um/uh in 30 min on top of the 34 written; on 300 real short words
  decoded alone it said "Uh" once (FP ~0.3 %). "Mm" / "Hmm" are useless as a signal (clipped words
  decoded alone come back "Mm." about 1 in 7), so only um/uh/er/erm/ah count.
- Limits: no labelled ground truth, so recall is unknown (fillers inside a word's span or glued to it are
  missed; known fillers decoded alone often come back "Yeah." / "Mm-hmm.", so this cannot confirm the
  ones the recogniser wrote). Mono 11 kHz test audio; real separate tracks should do better.
- Product: `features.build(hear=asr.Listener)` for English: `~filler 0.42s e+1 heard "Uh"` lines,
  `(1.11 ~filler)` on the pause it sits in, `heard "…"` on other `~snd` sounds; the English brief tells the
  AI to treat `~filler` like filler words (cut piled-up ones by raw seconds, keep a residue). Cost:
  ~15 s per 15 min track (4 vCPU, batches of 16 clips).

## Next
- Before the beta invitations: full English accuracy + depth test (Leon 2026-10-19), tracked as the last item of `docs/status/beta-launch-todo.md`.
- Calibrate on a human-edited English episode (cut rate, filler residue) when one is available.
- English show notes / poster copy.
