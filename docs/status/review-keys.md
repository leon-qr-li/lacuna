# Review shortcuts + progress (2026-10-17)

State: merged (PR #81, in releases since 2026.10.18.1); Leon's validation not recorded yet.

- Review page keys, one table in `web/src/features/review-keys/keys.ts`: Space play/pause, ← / → previous/next,
  K keep (or "don't cut" on an unapplied AI suggestion), R restore, A / B original/cut, S speed (PR #86, see
  `review-edit.md`), ? toggles the shortcut card.
  J (previous) and Y (keep) still work as quiet aliases. K used to mean "next"; it now means keep, per Leon's choice.
- Keys are ignored while typing (input, textarea, select, contenteditable) and with Ctrl/Cmd/Alt;
  K, R, Space, S and ? ignore key auto-repeat so holding K can't approve a run of edits.
- The floating dock shows 「已过目 x / y」 next to a "?" button that opens the shortcut card; the side panel
  progress bar was already there and stays.
- Test: `web/e2e/review_keys.spec.ts`.
