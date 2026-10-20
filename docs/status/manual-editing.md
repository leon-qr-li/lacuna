# 手动剪辑 (2026-10-19)

State: LIVE. PR #134 merged 2026-10-20 after Leon passed it on staging ("验收完毕，通过"); he plans to ask
for small follow-up features. Decision `manual-editing`.

- Backend: `lacuna_app/manual.py` (cut / silence a timeline range as one undoable edit; waveform tiles; transcript
  with cut words marked), routes `lacuna_app/routes/manual.py` (`GET …/manual/wave`, `GET …/manual/transcript`,
  `POST …/manual/cut`). Viewers (只听) are refused by the workspace role check like every other change.
- Web: `web/src/features/manual/` (EditLanes replaces the old `Lanes`, TranscriptEdit, SelBar, useManual for the
  shared selection); App.tsx only mounts them.
- Learning: manual cuts are `added` decisions with kind `manual`; their candidate rule says "你自己手动补剪了".
- Tests: `tests/app/test_manual.py`, `web/e2e/manual.spec.ts` (runs on the scopes server, its own state).
- English transcripts: words are spaced with `join_words` / `needsSpace` (from PR #132).
- Missing recordings (#138): wave / cut on an episode without its raw tracks get the usual 409 message.
- Not done (an idea, not asked): moving an existing cut's edges by dragging.

## Next version (Leon 2026-10-20 02:33Z "一到三开做"), PR #143 on staging
- One-word select: a click on a transcript word used to drop the selection and only seek, so a single 嗯 or a
  stutter could not be selected. Now a click selects that word and seeks; clicking it again drops it.
- 「暂停时回退 5 秒」 starts unticked (`usePlayer.ts` readPref: only a stored "1" turns it on).
- 剪辑时间线 (Leon 03:42Z picked "A + C" from the mock-up https://claude.ai/artifact/9iKfWjEn5kwgo7ZizP2SYV):
  zoom buttons and the hint line gone; Ctrl + wheel zooms smoothly around the pointer (span 3 s – 10 min,
  `lacuna.manual.span`) and never the page; a click no longer re-centres the window; pan = drag the ruler
  (`ml-ruler`), Space + drag / middle-drag on a lane, or the wheel; a Space tap without a drag still plays.
  Playback turns a page at the right edge. All in `EditLanes.tsx` (non-passive wheel + capture-phase Space listeners).
- Leon 04:24Z: while something is selected, play (▶, Space, 听选中) plays only the selection and returns the playhead
  to its start (`useManual.ts`, on the audio element's play event; voice-cut time, so it also works with music on).
- A "?" next to 剪辑时间线 explains clicking, selecting, zoom / pan, the marks and how AI and manual cuts are undone /
  restored / approved (`Help` in `EditLanes.tsx`, hover or keyboard focus).
