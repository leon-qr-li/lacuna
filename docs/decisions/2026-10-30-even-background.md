# Background music evened out (2026-10-30)

Leon (2026-10-30 21:38Z): some music suddenly gets loud, or louder and quieter by turns; even when it is already
down as background, a sudden loud bit must come down too, automatically, for all background (铺底) music.

* Where: every stretch where music plays as background under the talk: all of a bed, and the background part of an
  intro / interlude / outro. Full-level parts (intro alone, interlude in its gap, outro after 拜拜) and film clips
  keep the song's own dynamics. Applies to music already placed as well; nothing is stored, it is part of the mix.
* How (`levels.music_even`, `music.EpisodeMusic._even`): the song's level is the median of its 3 s level where it
  plays. A 1 s level more than 2 dB above it comes down by the excess (at most 12 dB), starting 0.5 s early; a 3 s
  level more than 2 dB under it comes up by the shortfall (at most 4 dB) unless it is 20 dB or more down (a pause
  in the music, never raised). Steps of 1 dB every 0.25 s at most, crossfaded over 0.1 s, as gain automation (Ducks)
  on the music track; the source file is untouched.
* Same batch: a new bed's default background level is 25 dB under full level (was 22; `music.BED_BG_DB`).
* 2026-10-31: back to 22 dB (Leon: "声儿有点太小了"); beds stored at 25 dB put back once at startup (`routes/bed_level_back_once.py`).
