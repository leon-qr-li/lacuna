# Prompt bar component; cover copy next to the audio (首次检测 23–25)

- **One input bar for "say it in a sentence" boxes**: `web/src/components/PromptBar.tsx` (+ `PromptBar.css`): GrowText on top, hint + mic + send inside the same framed bar, focus ring in the accent colour like the chat box. Callers pass translated strings, so the component adds no i18n keys. Only the poster page uses it for now; the edit chat keeps its own form to avoid clashing with parallel threads, and can switch later.
- `MicButton` gained an optional `idleIcon` (default 🎤, so other callers are unchanged); PromptBar passes an outline mic icon. Recording logic untouched.
- **「下载封面」 = browser download + a copy in the export folder.** Leon asked for the cover "in the same folder as the WAV/MP3", so the copy goes to `exports/<ep>/<ep>_cover.jpg` (same `<ep>_…` naming as the audio). The `publish/cover.*` originals stay as they are. Saving again overwrites the copy (atomic replace). The browser download is kept, since Leon said "not only" the browser download.
- Poster grid is fixed at 2 columns (4 versions = 2 rows); one column below 760 px.
