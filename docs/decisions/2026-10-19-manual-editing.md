# Manual editing: cut by hand on the waveform or the transcript, as ordinary edits

- Date: 2026-10-19
- Status: CONFIRMED（Leon 选了界面版本 2，2026-10-19 15:13Z）; the learning part is a Claude 技术决策
- Supersedes / changes: —

Leon wants to cut by hand ("一定要"), without losing anything the AI does. On 整集试听:

- **剪辑时间线** (was the two-track lane view): each host's real waveform (rendered on demand per 10 s tile,
  `lacuna_app/manual.py wave`), zoom 10 / 30 / 60 s, drag to select a stretch, a click still jumps there.
- **文字稿剪辑** (new card under the player, Leon's pick "版本 2"): the transcript around the playhead, one line
  per host run. Drag across words to select them, or click one word to select just it (a single 嗯 or a
  stutter; it also jumps there, a second click drops it — Leon 2026-10-20); words already cut (AI, chat or by hand) stay visible, struck
  through, and a click restores that edit.
- The selection bar: 删掉这段 (all tracks, the timeline closes up; key Del), 只静音 <host> (that host only,
  filled with their room tone, the timeline does not move), 听选中, 取消 (Esc).

A manual cut is an ordinary `Edit` (source `manual`, category `manual`, applied + approved, not consequential), so
undo / redo, 恢复 in 这附近改了什么 and the transcript, export, the AI producer's view of nearby edits and the
review lists all work unchanged; nothing of the AI first cut, review, chat or learned rules is replaced.
Boundaries snap to the quietest sample within 60 ms; a selection over an existing cut only cuts the rest.

Learning: a manual cut counts as a cut Leon added himself (verdict `added`, like a chat cut), so repeated hand
cuts of one host can become a *candidate* "AI 漏删了，你自己剪了" rule. As every rule, it changes nothing until he
approves it on 学到的规则 (decision `confirmed-learning`); habits are never deleted.
