# Bubble tour in the sample show (replaces the coach panel)

Date: 2026-10-22. Decided by Leon (「都用新版…重新设计你那个气泡式的 tour」, 「好嘞，做。」).

## Decision
- The sample show teaches with a **locked bubble tour**, not a side panel: everything is masked except the part
  the bubble talks about; on a step that asks for an action only that part can be clicked. One bubble per thing,
  and whatever a bubble mentions is lit up (e.g. 导出: the result and platform-standard cards on the right).
- It follows the real pages exactly (no mock-ups) through 9 chapters: raw 30 s → 审阅 (A/B, keep, progress,
  routine) → 整集试听 (timeline, legend, player, restore an automatic cut, transcript, 这附近改了什么) → 对 LACUNA
  说 (pending box, A/B, approve) → 手动删除 → 手动静音 (one host) → 声音 (adjusting is optional) → 配乐 (library,
  intro / outro, the curve's white dots, sliders and numbers, 更多设置, try, the final mix, ask LACUNA, adopt,
  defaults, credits) → 导出 (formats, start, download, summary, standard, publish) → before / after.
- Few cut points (five in the first cut, three to review) so the timeline doesn't look alarming.
- The two sentences the tour fills in (the actor lines; the intro under the talk) get **scripted answers** on the
  server for the sample episode only, so the tour never calls the AI, never uses quota and always works.
- The place reached is stored per person (`onboarding.tour`): leaving and coming back resumes it; "" = finished or
  left; 重新开始示例教程 resets the sample and starts again.
- Sample music: three CC0 tracks (John Bartmann), trimmed, checked against Leon's downloads by sha256.

## Why
Leon: the tour must be detailed, recreate day-to-day editing, never leave out a feature, light up what it talks
about, and be locked so a new person can't get lost.
