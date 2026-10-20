# 手动剪辑 (2026-10-19)

State: built on branch `claude/manual-editing-yx0i6o`, on staging for Leon's check. Decision `manual-editing`.

- Backend: `lacuna_app/manual.py` (cut / silence a timeline range as one undoable edit; waveform tiles; transcript
  with cut words marked), routes `lacuna_app/routes/manual.py` (`GET …/manual/wave`, `GET …/manual/transcript`,
  `POST …/manual/cut`). Viewers (只听) are refused by the workspace role check like every other change.
- Web: `web/src/features/manual/` (EditLanes replaces the old `Lanes`, TranscriptEdit, SelBar, useManual for the
  shared selection); App.tsx only mounts them.
- Learning: manual cuts are `added` decisions with kind `manual`; their candidate rule says "你自己手动补剪了".
- Tests: `tests/app/test_manual.py`, `web/e2e/manual.spec.ts` (runs on the scopes server, its own state).
- English transcripts: words are spaced with `join_words` / `needsSpace` (from PR #132).
- Not done (an idea, not asked): moving an existing cut's edges by dragging.
