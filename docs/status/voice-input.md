# Chat voice input

State: **done, validated by Leon 2026-10-17**

- **Chat voice input** (2026-10-17, D43): 🎤 button next to the chat box; local SenseVoice, text lands in the box, Leon sends. Needs the models from a first import (`<workspace>/models`). **Validated by Leon 2026-10-17.**
- **Context correction** (2026-10-18, backlog #10, decision `2026-10-18-dictation-context-fix.md`): after local recognition, Haiku fixes homophones and names using hosts, `names.json`, episode title/terms, transcript near the playhead and recent chat; falls back to the local text on any failure. Chat and poster 「一句话改」 both pass their episode. Code: `lacuna_app/dictation_fix.py`, `lacuna_app/routes/dictation.py`; tests `tests/app/test_dictation_fix.py`, `web/e2e/voice.spec.ts`. Not yet validated by Leon.
