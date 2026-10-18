# UI redesign: direction "C 轻盈 (Focus)", bundled fonts, light/dark theme

Date: 2026-10-17 · Phase 8 · Decided by Leon (picked C from four mockup directions, then "先按这版本改")

## Context
Leon: the UI is cramped (every button in the top bar), not intuitive, the Chinese font looks bad, and he wants a
modern, high-end look without more complexity, plus a dark and a light theme. English UI comes later (i18n thread
paused until this redesign lands), so layouts must not break with longer English labels.

## Decision
- Layout (round-2 mockups in `/mnt/project-files/lacuna/screenshots/phase8-ui/round2/`, source `mockups/c2.html`):
  no sidebar; a slim top bar (where you are + 素材库 / 学到的规则 / theme / 设置, and the AI 制作人 drawer on episode
  screens); one 5-step pipeline per episode: 审阅改动 → 整集试听 → 配乐 → 导出 → 发布 (发布 = sub-tabs 文案 / 海报 /
  上传喜马拉雅); a floating bottom dock carries playback plus the actions of the current step (review: prev, A/B,
  带配乐听, 恢复原话, 保留这个删除, next); each step ends with a "下一步" button.
- Fonts are bundled with the app (npm `@fontsource-variable/inter`, `@fontsource-variable/jetbrains-mono`,
  `misans`): Inter for Latin, MiSans VF for Chinese, JetBrains Mono for times. No web fonts: Google Fonts is
  unreachable in China, which is why Leon saw Microsoft YaHei. MiSans covers SC + many scripts (good for later
  localization) and is free for commercial use (Xiaomi MiSans licence); fallback stack ends in PingFang / YaHei.
  Cost: ~5 MB of woff2 in `web/dist`, loaded per unicode-range chunk.
- Theme: design tokens on `:root`, swapped by `html[data-theme="dark"]`; choice in localStorage `lacuna.theme`,
  default follows the OS; applied in `index.html` before first paint. Older token names stay as aliases so feature
  CSS keeps working in both themes.
- Delivered in small PRs (foundation → shell → pages), the review player / music page after the 6a thread's PRs.

## Rejected
A "Studio" (sidebar + 7 numbered steps), B "Cinema" (dark/gold, serif), D (A layout + B style). Mockups kept in
`/mnt/project-files/lacuna/screenshots/phase8-ui/round1/`.

Changed by: `2026-10-18-loudness-leveling` and `2026-10-18-confirmed-learning` — the flow is now 审阅改动 → 整集试听 → 声音 → 本集学到的规则 → 配乐 → 导出 → 发布 (发布 sub-tabs 发布资料 / 喜马拉雅版 / 海报 / 上传喜马拉雅, see `2026-10-18-ximalaya-show-notes`).
