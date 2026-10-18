# Music page: automatic / looping beds, changing a placement's use, one player (首次检测 15-22)

Date: 2026-10-18 · Status: decided (Leon handed the whole 首次检测 list over: "go nuts")

## Beds placed by the App (item 21)
- A bed added **without a position** is automatic (`auto: true`): it goes into the *free stretches*,
  the final-mix time where no other music plays (intro / interlude / outro / clips / manual beds, each
  over the whole time its song plays). Writing a position (or an end point) makes it a manual bed;
  ticking 「自动放进空档」 hands it back.
- Several automatic beds fill free time in the order they were added, one after the other; stretches
  shorter than 8 s are skipped. With no free time left the bed is kept but not played, and its row
  says so (`no_room`).
- `loop` (default off, as in PR #83): the song repeats to fill its stretch, each pass crossfading 2 s
  into the next (two alternating tracks, so passes may overlap; never more than a quarter of the song).
  An automatic looping bed fills its whole free stretch; a manual one fills to its end point, else to
  where the next music starts (or the talk ends). Without loop a bed plays once and fades out (3 s)
  where its stretch ends.
- Why: Leon wanted to pick a song as 铺底 and have it simply sit under the talk wherever nothing else
  plays, without typing times; manual positions still win.

## Changing a placement's use in place (item 22)
- The row's type picker changes the role. Kept: song, trim (src_in/out), volume (gain_db) and the
  background level (bg_db). Reset to the new role's defaults: solo_s, ramp_s, ramp_out_s, pre_s, bye_s,
  fade_out_s, lead_s (they mean different things per role).
- Position: interlude → bed keeps the point (manual bed); intro / outro → bed becomes automatic;
  → interlude / clip with no point yet goes to the best pause between topics (`break_candidates`), and
  can then be moved as usual. Choosing intro / outro while another exists replaces it; the option says
  「（替换现在的）」.

## Defaults and labels (items 16, 17)
- Background level for new placements 22 dB under full level (was 20). Saved placements keep their
  value; schema-1 files upgrade with the 20 dB they were heard with.
- Interlude 「正常音量（秒）」 → 「全音量时长（秒）」 (English "Full-volume length (s)").

## One player on the music page (items 18, 19)
- 「成品试听（含配乐）」 is the only player for the episode's music. Clicking a block on the strip or
  「试听这一处」 moves that player to 5 s before the placement's first transition (`listen_s`) and plays;
  clicking elsewhere on the strip jumps there. A playhead on the strip follows the player; −5 s / +5 s
  buttons and a clock sit under it. A new mix (after a change) keeps the position.
- Suggestions (drafts) are not in the mix yet, so they still play as a short clip of their own.

## Asset picker (item 15)
- Every option starts with the file name (never shortened): 「文件名 - 歌名 · 用途」, or
  「文件名 · 用途」 when only the file name is known.
