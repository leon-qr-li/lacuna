# Phase 10 — 海报

State: **done, validated by Leon 2026-10-17** (D49)

What Leon gets: Claude 按本期内容写 3–4 版极简 SVG 海报，本地渲染 PNG，Leon 挑一版或一句话改

Depends on: 9 · Parallel with: 6a

## Progress
- **Phase 10 cover built** (2026-10-17, D49): episode page 「海报」 → Claude draws 4 square covers in parallel (one emblem / side by side / geometry / free) from the publish pack's text, rendered locally with resvg + bundled Inter; zoom, change one with a sentence (typed or voice) → new version, 「用这张」 → `exports/<ep>/publish/cover.jpg` + `.png` + `.svg` at 3000×3000. Needs a publish pack first. Installed on Leon's PC (main 6020041) and **validated by Leon 2026-10-17** ("这功能不错").
- **首次检测 items 23–25** (2026-10-18, merged, waiting for the batched release): posters in a 2×2 grid (one column under 760 px); 「一句话改」 is now the shared `web/src/components/PromptBar.tsx` (wide growing box, mic + 改 inside one framed bar, Enter sends); 「下载封面」 on 上传喜马拉雅 also copies the cover to `exports/<ep>/<ep>_cover.jpg` next to the WAV/MP3 (`POST /api/episodes/<ep>/upload/save-cover`) and shows where. Poster page text says LACUNA / AI instead of Claude. See docs/decisions/2026-10-18-prompt-bar-and-cover-copy.md.
