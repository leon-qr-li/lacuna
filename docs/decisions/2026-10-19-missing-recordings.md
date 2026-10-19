# Missing recordings: a clear notice and a re-upload, never a 500

Date: 2026-10-19 · Status: accepted

## Context
On 2026-10-19 every place that plays sound on lacunastudio.app and staging failed for 生化危机 (PULSE-013):
整集 audio `net::ERR_ABORTED 520`, review clips (`/edits/*/ab`) and the music page (`/music`) 500, and
声音 / export likewise. The desktop app reads raw tracks where they lie (D29); PULSE-013's two tracks
are `C:\Users\liqin\Downloads\{Leon,Pei}_resident_evil.wav`. The move from the desktop (#127) uploaded
only the workspace folder and rewrote only paths inside it, so on the server those two paths point
nowhere. The episode still opened (its clipping-repair cache had come along), but anything that reads
audio raised; the WAV stream had already sent its headers, hence the 520. Not a regression of
#126 / #132: the episode never had its audio on the server. Confirmed by the files' sha256 on Leon's PC
matching the episode's media ids.

## Decision
- `Episode.missing_sources()` lists recordings whose file is not on this machine; the episode summary
  carries it as `missing_sources`.
- Rendering with a recording missing raises `MissingSources` (409, says what to do); the WAV stream
  checks before sending headers; any unreadable recording (libsndfile error) answers 409, not 500.
- `POST /api/episodes/{id}/sources?name=&part=` takes an original file (in pieces when big), matches it
  by content (media id = sha256 of the bytes), keeps it in `<episode>/media/` and points the episode at
  it. Anything else is refused (422). Code: `lacuna_app/sources.py`, `routes/sources.py`.
- The episode page shows a banner naming the missing files with one upload button
  (`web/src/features/sources/`); after the last one it reloads so the players start afresh.
