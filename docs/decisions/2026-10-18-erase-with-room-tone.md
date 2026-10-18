# Erasing one host's sound fills it with that host's own room tone

- Date: 2026-10-18
- Status: Leon's ask in the first full test (backlog item 8); mechanism and numbers are Claude's defaults

- New edit op `erase` (`EraseRange`): removes [start, end) on one track only (nothing moves, the other host is
  untouched) and fills exactly the removed material with a stretch of **the same track's own source** that has no
  words and no transients (scored on its loudest 10 ms frame), is not digital silence, and lies within 30 s of the
  edit (closer wins over slightly quieter). The stretch is 0.3–1.5 s long, repeated if the erase is longer. Seams use
  the renderer's usual 16 ms equal-power crossfade. It only references source audio, so the EDL rules hold.
- The tone range is stored in the op (`tone_media_id`, `tone_src_in`, `tone_src_out`), so the saved state stays the
  exact render recipe; it is picked when the edit is created (`Episode.add_edit`, `create_episode`).
- Every one-track removal now uses it: the AI first cut's one-host cuts (crosstalk, 嗯 / 对 backchannel, noise)
  and the chat's `cut_one_track` ("抹掉 Pei 那几个嗯"). An adopted rule like "trim Pei's repeated 嗯 with room
  tone" therefore just works: the first cut makes a one-track cut, which becomes an erase.
- Why not the track-level `RoomTone` the engine already had: it fills *every* interior gap, including the gap opened
  for an interlude, where host hiss under the music would be wrong.
- Episodes created before this keep their plain lifts (silence) until re-imported; nothing is rewritten silently.
- Review: an erase shows on that host's lane only, with a 「只抹 Pei，用底噪补上」 chip, and restores like any edit.
