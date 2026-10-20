# 整集试听 as a one-screen workbench (version B)

- Date: 2026-10-20
- Status: Leon picked version B (18:55Z) out of A / B / C; he asked for 「下一步」 at the top right on every step (18:56Z)
- Mockups: project files `lacuna/screenshots/listen-layout/` (A = his three-tab proposal, B = recommended, C = Descript-style)

The page used to scroll up and down: overview, timeline, player, transcript and 这附近改了什么 were stacked cards, so
cutting a word, checking the waveform and looking at nearby edits meant scrolling back and forth. Audio editors
(Audition, Audacity) keep the waveform as the big central workbench and fit the window; text-first editors
(Descript, Riverside) dock the timeline under the transcript.

- **One screen.** On 整集试听 the page is exactly the window height; each part scrolls inside itself. Short (≤600px)
  or phone-width (≤760px) windows fall back to a normal scrolling page.
- **Timeline on top, transcript under it.** The two most used editing tools are always visible together (selecting
  words is selecting waveform). The lanes share the timeline card's height, so they are much taller than the old
  44 px strips.
- **Minimap.** 整集概览 (or 话题段落) is no longer its own card: a thin strip in the timeline card above the ruler,
  same ticks and click-to-jump; its hint moved into the tooltip.
- **Player inside the timeline card**, under the legend, next to the waveform it controls; 带配乐听 stays with it.
- **Side panel tabs: AI 制作人 / 这附近改了什么.** The transcript is not a tab (it would hide behind the chat); the
  nearby list is, with its count on the tab. The conversation stays mounted while the other tab is open; the tab is
  remembered (`lacuna.side.tab`). 收起 and the floating reopen button (#150) are unchanged; in English 收起 shows
  only its arrow so the tabs fit.
- **Edit card on the timeline.** Pointing at a cut (within 6 px) opens a small card: what it is, its status,
  ▶ 听前后 (plays from 3 s before) and 恢复 / 重新应用. Most of what the nearby list was used for is now one step
  from the waveform, which is why that list can live in a tab.
- **下一步 at the top right on every step**, after 撤销 / 重做 / 导出 (no longer at the page bottom).
