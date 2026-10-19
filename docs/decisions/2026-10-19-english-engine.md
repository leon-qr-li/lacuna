# English episodes: the episode's language picks the engines

**Date:** 2026-10-19 · **Asked by:** Leon (future direction 3, multi-language engines; his market is global)

## Decision
- **Language per episode.** The show profile has a `language` (`zh` default, `en`); the import form can
  change it for one episode. The import job and the episode (`episode.json` `language`) keep it.
- **English speech recognition:** Parakeet-TDT 0.6B v2 int8 (sherpa-onnx, CPU, ~480 MB download) as the main
  recogniser, SenseVoice locked to `en` as the cross-check, the same Silero VAD. Chosen on the
  2026-10-19 measurement (`英文剪辑实测_2026-10-19.md`): 15 % WER against 111 % for Paraformer-zh on English.
  Models download on the first English import (zh models are not needed for an English workspace).
- Sentencepiece pieces are merged into **one token per word** in `asr.py`; English words keep their
  punctuation ("experience,"). The two recognisers are compared on lower-case words without punctuation.
- **AI brief:** an English episode, in any show (Leon's included), gets `prompts/first_cut_brief_en.txt` +
  `first_cut_defaults_en.txt` (English fillers, discourse markers, restarts) with the show's hosts and
  strictness; Leon's EP001 calibration is Chinese and is not used for English. Reasons stay in the
  interface language (Chinese unless the interface is English), as before.
- **Display:** words are joined with a space only where both sides are Latin (`lacuna_app/words.py`,
  `web/src/words.ts`): Chinese reads as before, English gets spaces (review text, titles, chat, show-notes
  transcript, learned-habit examples).

## Not yet
- um/uh that the recognisers drop (both drop most): a detector is the next step (spike).
- Calibrating the English defaults on a human-edited English episode (none available yet).
- Show notes / poster prompts for an English show still write Chinese copy.
- Other languages (the engine table `asr.ENGINES` takes more).
