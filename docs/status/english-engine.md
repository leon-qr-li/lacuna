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

## Next
- um/uh detector spike (recognisers drop most fillers; `~snd` sounds inside a sentence are the candidates).
- English show notes / poster copy.
