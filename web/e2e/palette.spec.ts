import { expect, test } from "@playwright/test";

// UI colors follow the logo (V3 光晕): navy for primary buttons, sunset as the highlight, no blue-violet accent;
// every text/background token pair stays readable (WCAG AA 4.5:1) in both themes.
const PAIRS: [string, string][] = [
  ["--on-primary", "--primary"],
  ["--accent-ink", "--accent-soft"],
  ["--accent-ink", "--solid"],
  ["--warn", "--warn-soft"],
  ["--warn", "--solid"],
  ["--ok", "--ok-soft"],
  ["--danger", "--solid"],
  ["--ink-2", "--solid"],
  ["--pei-ink", "--solid"],
];

for (const theme of ["light", "dark"] as const) {
  test(`palette (${theme}): logo colors and readable contrast`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme });
    await page.goto("/#/");
    await page.evaluate((t) => localStorage.setItem("lacuna.theme", t), theme);
    await page.goto("/#/settings");
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);

    const res = await page.evaluate((pairs) => {
      // resolve a token to sRGB through a probe element (handles hex, rgb() and alpha over --solid)
      const probe = document.createElement("div");
      document.body.appendChild(probe);
      const rgb = (v: string, over?: number[]): number[] => {
        probe.style.color = `var(${v})`;
        const m = getComputedStyle(probe).color.match(/[\d.]+/g)!.map(Number);
        const a = m.length > 3 ? m[3] : 1;
        const base = over ?? [255, 255, 255];
        return [0, 1, 2].map((i) => m[i] * a + base[i] * (1 - a));
      };
      const lum = (c: number[]) => {
        const [r, g, b] = c.map((x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; });
        return 0.2126 * r + 0.7152 * g + 0.0722 * b;
      };
      const bg = rgb("--bg");
      const solid = rgb("--solid", bg);
      const ratio = (fg: string, back: string) => {
        const b = rgb(back, solid);
        const f = rgb(fg, b);
        const [hi, lo] = [lum(f), lum(b)].sort((x, y) => y - x);
        return Math.round(((hi + 0.05) / (lo + 0.05)) * 100) / 100;
      };
      const out = Object.fromEntries(pairs.map(([f, b]) => [`${f} on ${b}`, ratio(f, b)]));
      const css = getComputedStyle(document.documentElement);
      const result = { ratios: out, grad: css.getPropertyValue("--grad"), accent: rgb("--accent"), primary: rgb("--primary") };
      probe.remove();
      return result;
    }, PAIRS);

    for (const [k, v] of Object.entries(res.ratios)) expect(v, k).toBeGreaterThanOrEqual(4.5);
    // the brand gradient is the logo's sunset, and the accent is warm (red channel leads, not blue)
    expect(res.grad.toLowerCase()).toContain("#ff7a3d");
    expect(res.accent[0]).toBeGreaterThan(res.accent[2] + 80);
    // light theme: primary buttons are the logo navy; dark theme: near-white
    if (theme === "light") expect(res.primary.map(Math.round)).toEqual([22, 27, 69]);
    else expect(res.primary[0]).toBeGreaterThan(230);
  });
}
