# Even host loudness from import on; per-track gain; music levelled on what plays

- Date: 2026-10-18
- Status: Claude's defaults under Leon's "go nuts" (首次检测 backlog items 7 and 20)
- Code: `lacuna_app/levels.py`, `lacuna_app/routes/levels.py`, `web/src/features/levels/`

## Voice (item 7)
- At import, after the episode is built, each host track of the uncut recording is measured (BS.1770 integrated
  loudness on the dual-mono scale the music code already uses, sample peak, a robust "loud peak" = 99.9th
  percentile of 10 ms maxima, clipped runs) and gets a `track_gain` edit so both sit at **−20 LUFS**. Review
  playback and export hear the same balance from the first listen. The gains are part of the episode's first
  state (no undo step); category `loudness`, source `level`.
- A gain never pushes a track's loud peaks over the renderer's soft-clip knee (−1 dBFS). If one host can't reach
  the target, both aim lower by the same amount (at most 6 dB), so they stay even.
- Older episodes are not changed automatically; 「声音」 shows the difference and a 「统一两人音量」 button.
- 「声音」 step (after 整集试听): per-track gain slider / ±1 dB / suggested value, loudness now vs raw, clipped
  spots. The editing chat understands "我的声音太低", "Pei 大一点 3 dB", "两人音量统一一下" locally (no AI call,
  no cost): it changes the gain at once as an undoable step and says so. Default step 2 dB, "稍微" 1 dB, "我" = the
  first host track (Leon). Requests that mention music (配乐 / 音乐 / 背景 …) or cutting are left to the AI editor.
- At most one `track_gain` edit per track is in effect; a change discards the previous one in the same undo step.
  Volume edits are not editing decisions, so learning ignores them.
- **No compression at import.** Compression changes the conversation's dynamics and the EDL can only reference
  source audio; the export chain (`lacuna_core/master.py`: −16 LUFS, −1 dBTP, light 2:1) already does it on the
  final mix. Gains don't stack with mastering: the master measures the whole mix and normalises it again, so
  these gains only set the balance (and what review sounds like).
- **Clipping is detected, not repaired.** Reconstructing flattened peaks needs a processed copy of the source,
  and a bad repair sounds worse than the click. 「声音」 lists the spots (times on the current cut, click to hear
  from 2 s before) and suggests recording that track lower next time.

## Music (item 20)
- Full level stays "about 1 LU under the voice" (D45), but the song's loudness is now measured on the part that
  plays (`src_in_s`..`src_out_s`) instead of the whole file, so a quiet opening isn't left quiet because the
  finale is loud. Songs whose library measurement is missing are measured on use. Because the voice loudness is
  measured on the current cut, music follows the import levelling automatically.
- 「音量（dB）」 stays Leon's offset on top; the automatic part is exposed as `level_db` on each placement.
