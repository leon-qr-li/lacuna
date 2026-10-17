// Renders web/src/features/brand/logo.svg to PNGs for the desktop icons (then make_icons.py packs
// installer/LACUNA.ico + installer/LACUNA.icns). Run from the repo root:
//   node design/logo/render_icons.mjs && python design/logo/make_icons.py
import { chromium } from "playwright";
import { readFileSync, mkdirSync } from "node:fs";
const svg = readFileSync("web/src/features/brand/logo.svg", "utf8");
mkdirSync("design/logo/png", { recursive: true });
const b = await chromium.launch();
for (const s of [16, 24, 32, 48, 64, 128, 256, 512, 1024]) {
  const p = await b.newPage({ viewport: { width: s, height: s } });
  await p.setContent(`<style>html,body{margin:0;background:transparent}svg{display:block;width:${s}px;height:${s}px}</style>${svg}`);
  await p.screenshot({ path: `design/logo/png/logo_${s}.png`, omitBackground: true });
  await p.close();
}
await b.close();
