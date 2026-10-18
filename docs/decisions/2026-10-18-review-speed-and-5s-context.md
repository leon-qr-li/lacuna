# Review player: speed 1× / 1.25× / 1.5× / 2×, and 5 s either side of an edit

- Date: 2026-10-18
- Status: Leon's asks in the first full test (backlog items 6 and 11); the exact speeds and key are Claude's defaults

- The review dock's A/B player gets a speed chip that steps 1× → 1.25× → 1.5× → 2× → 1× per tap; **S** does the same
  and is listed in the "?" shortcut card. Pitch is kept (`preservesPitch`). The choice is remembered in this browser
  (`localStorage` `lacuna.reviewRate`) and applies to every edit and to A and B alike.
  One chip instead of four buttons: the dock must still fit on one row with the longer English labels.
- The full-listen player keeps its own 1× / 1.5× buttons (unchanged).
- Every before/after excerpt (review A/B, chat proposal preview) renders **5 s** either side of the edit instead of
  10 s (`Episode.ab` / `Previewer.around` defaults). The 80 s cap for long edits is unchanged.
