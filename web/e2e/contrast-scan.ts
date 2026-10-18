import type { Page } from "@playwright/test";

// every enabled button (and link styled as one) has readable text: WCAG AA 4.5:1 against the
// nearest solid background (gradient buttons: their text against every stop of the gradient).
// Shared by contrast.spec.ts (every screen) and specs that check their own dialogs.
export async function scan(page: Page) {
  return page.evaluate(() => {
    const parse = (c: string) => {
      const n = (c.match(/[\d.]+/g) ?? []).map(Number);
      // color(srgb r g b / a) uses 0–1 channels
      return c.startsWith("color(") ? [...n.slice(0, 3).map((x) => x * 255), ...n.slice(3)] : n;
    };
    const lum = (c: number[]) => {
      const [r, g, b] = c.slice(0, 3).map((x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; });
      return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    };
    const blend = (top: number[], under: number[]) => {
      const a = top.length > 3 ? top[3] : 1;
      return [0, 1, 2].map((i) => top[i] * a + under[i] * (1 - a));
    };
    const ratio = (a: number[], b: number[]) => {
      const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
      return (hi + 0.05) / (lo + 0.05);
    };
    // the background seen behind el: stack translucent layers from the page up
    const backdrop = (el: Element): { rgb: number[]; grad?: string } => {
      const chain: Element[] = [];
      for (let e: Element | null = el; e; e = e.parentElement) chain.push(e);
      const root = parse(getComputedStyle(document.documentElement).getPropertyValue("--bg").trim() ? getComputedStyle(document.body).backgroundColor : "rgb(255,255,255)");
      let rgb = root.length >= 3 && (root[3] ?? 1) > 0 ? root.slice(0, 3) : [255, 255, 255];
      for (const e of chain.reverse()) {
        const cs = getComputedStyle(e);
        const bg = parse(cs.backgroundColor);
        if (bg.length >= 3 && (bg[3] ?? 1) > 0) rgb = blend(bg, rgb);
        if (e === el && cs.backgroundImage.includes("gradient")) return { rgb, grad: cs.backgroundImage };
      }
      return { rgb };
    };
    const bad: string[] = [];
    let n = 0;
    for (const el of document.querySelectorAll<HTMLElement>("button, a.btn, .btn")) {
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height || (el as HTMLButtonElement).disabled || !el.innerText.trim()) continue;
      if (getComputedStyle(el).visibility === "hidden") continue;
      const cs = getComputedStyle(el);
      const { rgb, grad } = backdrop(el);
      const fg = blend(parse(cs.color), rgb);
      let worst: number;
      if (grad) {
        const stops = (grad.match(/rgba?\([^)]+\)/g) ?? []).map(parse).map((c) => blend(c, rgb));
        worst = Math.min(...stops.map((s) => ratio(fg, s)));
        // white text on the brand gradient: at least 4:1 on every stop (bold button text)
        if (worst < 4) bad.push(`${el.innerText.trim().slice(0, 20)} [gradient] ${worst.toFixed(2)}`);
      } else {
        worst = ratio(fg, rgb);
        if (worst < 4.5) bad.push(`${el.innerText.trim().slice(0, 20)} [${el.className}] ${worst.toFixed(2)}`);
      }
      n++;
    }
    return { n, bad };
  });
}
