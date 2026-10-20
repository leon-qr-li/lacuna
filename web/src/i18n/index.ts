/**
 * Interface language (中文 / English).
 *
 * Every user-facing string is written in Chinese and wrapped in `t("中文")`; the Chinese text is the
 * key, so code stays readable and Chinese needs no dictionary. English lives next to the code that
 * uses it: `src/i18n/en.ts` for the shell and shared components, `src/features/<name>/en.ts` for a
 * feature. Missing English falls back to Chinese; `npm run build` runs `scripts/i18n-check.mjs`,
 * which fails on hard-coded Chinese outside `t()` and on keys with no English.
 *
 * The choice is kept in localStorage and in a cookie (so the server answers errors and AI replies in
 * the same language). Switching reloads the page, so `t()` is a plain function usable anywhere.
 */
export type Lang = "zh" | "en";
/** A translation: plain text, or singular / plural picked by the `n` parameter. */
export type Entry = string | { one: string; other: string };
export type Dict = Record<string, Entry>;
type Params = Record<string, string | number | null | undefined>;

const KEY = "lacuna.lang";
const COOKIE = "lacuna_lang";

function readSaved(): Lang | null {
  try {
    const v = localStorage.getItem(KEY);
    return v === "zh" || v === "en" ? v : null;
  } catch {
    return null;
  }
}

/** Chinese unless English was chosen in 设置 (the show and its hosts are Chinese). */
export const lang: Lang = readSaved() ?? "zh";
/** Nobody has picked a language in this browser yet (an invite link may pick it). */
export const langChosen = readSaved() !== null;
export const locale = lang === "en" ? "en-US" : "zh-CN";

const mods = import.meta.glob<{ en: Dict }>(["./en.ts", "../features/*/en.ts"], { eager: true });
const EN: Dict = Object.assign({}, ...Object.keys(mods).sort().map((k) => mods[k].en));

const fill = (s: string, p?: Params) => (p ? s.replace(/\{(\w+)\}/g, (m, k) => (k in p ? String(p[k] ?? "") : m)) : s);

/** `t("删除 {n} 处", { n })` → "删除 3 处" / "3 edits removed". */
export function t(zh: string, params?: Params): string {
  if (lang === "zh") return fill(zh, params);
  const e = EN[zh];
  if (e === undefined) return fill(zh, params);
  if (typeof e === "string") return fill(e, params);
  return fill(Number(params?.n) === 1 ? e.one : e.other, params);
}

/** Date + time in the interface language. */
export const fmtDateTime = (d: string | number | Date) => new Date(d).toLocaleString(locale);

export function setLang(l: Lang): void {
  try {
    localStorage.setItem(KEY, l);
  } catch {
    /* private mode: the cookie still carries it for this session */
  }
  document.cookie = `${COOKIE}=${l}; path=/; max-age=31536000; samesite=lax`;
  location.reload();
}

// keep the cookie and <html lang> in step with the saved choice (also after an update)
document.cookie = `${COOKIE}=${lang}; path=/; max-age=31536000; samesite=lax`;
document.documentElement.lang = lang === "en" ? "en" : "zh-CN";

/** "a、b、c" / "a, b, c". */
export const joinList = (xs: string[]) => xs.join(lang === "en" ? ", " : "、");
