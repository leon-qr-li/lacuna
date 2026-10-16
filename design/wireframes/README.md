# Low-fi wireframes v1 (2026-10-16)

Published canvas: https://claude.ai/artifact/1BvHmxW54dWCS9kFPyumqV (private to Leon).
Source of the five artboards is mirrored here (`*.dc.html`, `canvas.json`); the canvas is the editable original.

Key UX decisions (Claude-owned, pending Leon's review of the primary journey):
- One episode workspace; Full Listen and Edit Review are two modes sharing playhead and history.
- Chat is anchored to the playhead (`@ 42:10`); every AI change returns as before/after preview + approve.
- Edit Review lists only consequential edits (content cuts, interjection moves/deletes) ranked by impact; routine cleanup is summarised by category, never approved one by one; "deliberately kept" uncertain spots are surfaced too.
- Original words shown read-only with strike-through for cuts; no transcript rewriting anywhere.
- Missing assets become non-blocking tasks with a pre-created folder and a description of the desired feeling, not invented timestamps.
- Learned habits are batched for review after an episode, with evidence and confidence; precedence: episode > series > global > unconfirmed.
