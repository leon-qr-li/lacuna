# 间隙 (2026-10-30)

State: built, PR open. Leon asked 2026-10-30 21:05Z ("现在就做吧，我现在正好需要这个功能"), picked direction A and the
details in decision `2026-10-30-edit-gaps` at 21:15Z. He needs it on an episode he has already finished editing.

- Backend: `lacuna_app/gaps.py` (gaps.json store), `lacuna_app/routes/gaps.py` (`GET/POST …/gaps`,
  `PATCH/DELETE …/gaps/{id}`, `POST …/music/gaps/auto`), layout / mix / export key in `lacuna_app/music.py`,
  `fill_gaps` in `music_assist.py`, the export holds its gaps like its placements (`exporter.py`).
- Web: `web/src/features/gaps/` (marks, right-click menu, card, transcript row / 「＋」, 配乐 banner and strip,
  export check); hooks in `manual/EditLanes.tsx`, `manual/TranscriptEdit.tsx`, `library/MusicView.tsx`,
  `library/MusicCard.tsx`, `library/useMusicListen.tsx`, `components/ExportPanel.tsx`.
- Tests: `tests/app/test_gaps.py` (voice edit files byte-identical, silence in the gap, gaps follow later cuts,
  fill keeps the length, removal restores the mix / export keys), `web/e2e/gaps.spec.ts`.
- Safety for Leon's finished episode: no migration; an episode without gaps.json has the same mix key, export key
  and layout as before (checked by the tests). Before the deploy his episode's edits + music.json are backed up.
- Not done: dragging a gap's edges on the timeline (the voice cut has no room for it; length is set on its card).

## Same PR: 铺底 a little lower (Leon 2026-10-30 21:36Z)
- A new bed's background default is 25 dB under full level (`music.BED_BG_DB`), was 22 dB (`BG_DB`, still used by
  intro / interlude / outro background). Placed beds keep their stored `bg_db`.
- Next (asked 21:39Z, own PR): level the music under the talk so a sudden loud passage of a bed is turned down too.
- Next (design asked 21:35Z): 自动铺底 from songs Leon picks, into the stretches not taken by 片头 / 片尾 / 间隙.
