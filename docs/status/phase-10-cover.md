# Phase 10 — 海报

State: **built (D49)**; install with the next batch update, then Leon validates

What Leon gets: Claude 按本期内容写 3–4 版极简 SVG 海报，本地渲染 PNG，Leon 挑一版或一句话改

Depends on: 9 · Parallel with: 6a

## Progress
- **Phase 10 cover built** (2026-10-17, D49): episode page 「海报」 → Claude draws 4 square covers in parallel (one emblem / side by side / geometry / free) from the publish pack's text, rendered locally with resvg + bundled Inter; zoom, change one with a sentence (typed or voice) → new version, 「用这张」 → `exports/<ep>/publish/cover.jpg` + `.png` + `.svg` at 3000×3000. Needs a publish pack first. Merged; install with the next batch update (`pip install -e .` pulls resvg-py + Pillow), then Leon validates with the real key (cost per round to be measured).
