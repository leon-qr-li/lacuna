# 自定义快捷键 + 误加间隙 — status

Decision: `docs/decisions/2026-11-02-custom-shortcuts.md`. Design page https://claude.ai/artifact/4u5fnqbQqmLNjhCcxj1dSn
(Leon took every recommendation on 2026-11-02).

## State (2026-11-02)
- PR 1 (#241): gaps added by mistake. ＋ in the transcript is only the dot and asks for the length; Shift+G instead
  of G; 「已加入 N 秒间隙」 toast with 撤销, Ctrl+Z takes back the gap added last (`web/src/features/gaps/lastAdd.ts`).
- PR 2: 设置 → 快捷键 (`web/src/features/shortcuts/`), `GET/PUT /api/shortcuts` (`lacuna_app/routes/shortcuts.py`,
  `shortcuts.json` in the person's home, only changed keys). All handlers read `keysOf` / `matches` / `hit`:
  App.tsx (play, ±5 s, undo / redo), manual/useManual.ts (cut), manual/EditLanes.tsx (gap; Space tap plays only
  while Space is the play key), transcript-search (find), review-keys/keys.ts (review page). Both "?" cards show
  the person's keys and link to `#/settings/keys`.

## Where things are
- The action table and defaults: `web/src/features/shortcuts/keys.ts` (`ACTIONS`). Add a new customizable key
  there, then read it with `matches(e, "<id>")`.
- Fixed on purpose: Esc, mouse gestures (Ctrl+wheel, Space+drag, right-click, edge drag).
- Browser keys refused: `RESERVED` in keys.ts.

## Open
- The transcript search box's aria-label still says Ctrl+F when the key is changed (visible text has no key).
