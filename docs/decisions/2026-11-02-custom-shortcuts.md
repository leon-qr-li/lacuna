# 自定义快捷键 + 误加间隙 (custom shortcuts, gaps added by mistake) — 2026-11-02

Leon (2026-11-02) asked for customizable editing shortcuts, and passed on a user's feedback: 「我就记得有个➕gap的
shortcut 我总是误点」. Design page https://claude.ai/artifact/4u5fnqbQqmLNjhCcxj1dSn; Leon took every
recommendation (「都按推荐」), then said 开始做.

## Gaps added by mistake (PR 1)
Two causes: the transcript's 「＋ 在这里加入间隙」 was a full-width 22 px invisible button between every two lines
(one click added 15 s), and a bare G added a gap at the playhead anywhere on the page. Gaps are outside the
episode's undo history, so Ctrl+Z could not take one back.
- Only the small ＋ dot is a button; it opens a menu to pick the length (5 / 10 / 15 / 30 s / other). Nothing is
  added before a length is picked; Esc or a click elsewhere closes it.
- The playhead key is Shift+G (G alone does nothing).
- After a gap is added: toast 「已加入 15 秒间隙」 with 撤销; Ctrl+Z also takes back the gap added last
  (`web/src/features/gaps/lastAdd.ts`). Any later change of the episode, or changing / removing that gap, ends it:
  Ctrl+Z then undoes the episode's own steps as before. Only the latest gap, no redo.

## Custom shortcuts (PR 2)
- Entry: 设置 → 个人 → 快捷键 (under 剪辑习惯), plus 「自定义快捷键」 at the foot of both "?" cards (edit timeline,
  review page), which jump there.
- Scheme A: a list grouped by page (播放 / 剪辑 on the listen-and-edit page, 撤销 everywhere, 审阅 on the review
  page); click a key to record a new one. Up to 2 keys per action; a key can be removed (the action then has none).
- Only keyboard keys change; mouse actions (Ctrl+wheel, Space-drag, right-click, dragging) and Esc stay fixed.
- Saved with the account (same on every computer); each member has their own. Ctrl means ⌘ on a Mac.
- A key already used on the same page: a popover offers 「改用在这里」 (the other action loses it) or 取消.
- Browser keys (Ctrl+W / T / N / R / L / Q / P, F5, F11, F12 …), Enter and Tab can't be set.
- 「全部恢复默认」 (in-app confirm) and ↺ per action. The "?" cards show the user's own keys.
