# 逐字稿搜索 in 整集试听

Leon 2026-10-31 picked direction A of the design page (an always-there search box on 逐字稿剪辑), with one
condition: it must not take much room. Built as a pill the size of the chips beside it (about 120 px idle,
about 240 px while searching), not the wide box of the sketch.

- Server: `GET /api/episodes/{id}/transcript/search?q=&v=` (`lacuna_app/transcript_search.py`) searches the whole
  transcript of that version, line by line, ignoring case, full/half width, spaces and punctuation. Cut words are
  found too and tagged `gone` (they stay visible, struck through). At most 500 places.
- Web (`web/src/features/transcript-search/`): typing marks every place in the transcript and as small ticks on the
  timeline ruler; Enter / ↓ jumps to the next place after the playhead, Shift+Enter / ↑ back (both wrap), Esc clears.
  Ctrl+F / ⌘F in 整集试听 focuses the box instead of the browser's find. A jump moves the playhead only: playing
  stays playing, paused stays paused.
- Not built (direction B/C): speaker filter, result list.
