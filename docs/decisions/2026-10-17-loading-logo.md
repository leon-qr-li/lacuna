# Loading indicator follows the logo (style C「信号」)

Date: 2026-10-17 · thread「统一的加载提示」 · supersedes the look (not the API) of `2026-10-17-unified-loading.md`

Leon (20:21Z): the 声波 bars felt off next to the new V3「光晕」 logo; redesign the loading indicator from the logo.

Mockups (light + dark, page load / button wait / long job): `screenshots/loading-v2/` — A 描线 (line draws and
retracts), B ON AIR (dot ripples), C 信号 (faint pulse line, a sunset-gradient glint runs along it, ON AIR dot breathes).

Decision: **C**. Recommended because it reads as "in progress" at 20 px and at 76 px and is closest to the logo itself;
B is almost invisible when small. Built while waiting for Leon's pick; A/B are in `mockups/loading2.html` if he
chooses otherwise.

- `Wave` keeps its name and props; it now draws the logo's pulse path (`L`+`A` stroke) with the logo gradient,
  a moving `stroke-dasharray` signal (`pathLength=100`), a blurred glow at `lg`, and the ON AIR dot.
- Progress bar fill and the top line use the same sunset gradient (`--ld-sun`).
- No page changes; reduced-motion users see the static mark.
