# Music plays whole; under talk it is constant background, not ducked away

- Date: 2026-10-18
- Status: Leon 产品决定 (thread "配乐完整播放", 2026-10-18 00:03Z: "凡是我上传的东西，一定要从头放到尾"), numbers are Claude's defaults pending his answers
- Supersedes / changes: D45 (default length caps, overlap with the voice, speech-driven ducking for intro / interlude / outro / bed)

- Every placement plays `src_in_s`–`src_out_s`, default the **whole file** (the 30 / 20 / 60 / 120 s caps are gone).
  Leon trims by setting 「裁到」; a trimmed end fades out (`fade_out_s`, default 10 s for the outro, 3 s otherwise).
- Under talk the music is **background**: `bg_db` (default 20 dB) under its full level, constant, no ducking that
  follows the speech. Full level stays measured: ~1 LU under the voice; `gain_db` on top.
- Intro: full level alone for `solo_s` (default 10 s), down to background over `ramp_s` (default 2 s); the voice
  starts there and the song plays on to its end.
- Interlude: at Leon's point the talk stops; the song rises over `ramp_s`, plays full for `solo_s` (default 15 s),
  falls over `ramp_out_s` (its own number, default = `ramp_s`), the talk resumes over it and it plays on to its end.
  Inserted time = ramp_s + solo_s + ramp_out_s.
  `pre_s` (default 0) lets it already play under the talk before the point.
- Outro: background under the last words, placed so the voice ends at `bye_s` of the file (default 30 s before its
  end); then rises over `ramp_s` and plays to `src_out_s`.
- Bed: background (`bg_db` lower) the whole way from its position to its end point or the end of the song.
- Clip (film line): unchanged.
- `music.json` schema 2. Schema-1 files and series rules upgrade on read (`music.upgrade_v1`): a length that was only
  the automatic cap becomes the whole file; the voice still comes in / resumes / ends where it did.
- Show notes (phase 9) keep reading times from the music layout (`music.final_time`): the intro's music-alone
  seconds and every interlude gap push later timestamps. The pack now also remembers the inserted time
  (`music_inserts`), so changing a gap or the intro length flags the timestamps stale even when the BGM lines
  stay the same; 「更新时间戳」 re-times locally. An interlude's timestamp / BGM line is where the talk stops,
  not where it started under the talk (`pre_s`).

Changed by: `2026-10-18-bed-auto-loop` (new placements default to `bg_db` 22 dB; beds can be automatic / looping) and `2026-10-18-loudness-leveling` (full level measured on the part that plays).
