/**
 * The admin's interface language (中文 / English, decision 2026-10-24-admin-site: English colleagues may join).
 * Same rule as the app (src/i18n): Chinese is the key, `t("中文")`, English in `en.ts` next to it; `npm run build`
 * checks both. The choice is the admin's own (localStorage), and a cookie tells the server for its error messages.
 */
import type { Dict, Lang } from "../i18n/index";
import { en as EN } from "./en";

const KEY = "lacuna.admin.lang";
type Params = Record<string, string | number | null | undefined>;

function saved(): Lang {
  try {
    const v = localStorage.getItem(KEY);
    return v === "en" ? "en" : "zh";
  } catch {
    return "zh";
  }
}

export const lang: Lang = saved();
export const locale = lang === "en" ? "en-US" : "zh-CN";
const dict: Dict = EN;
const fill = (s: string, p?: Params) => (p ? s.replace(/\{(\w+)\}/g, (m, k) => (k in p ? String(p[k] ?? "") : m)) : s);

export function t(zh: string, params?: Params): string {
  if (lang === "zh") return fill(zh, params);
  const e = dict[zh];
  if (e === undefined) return fill(zh, params);
  if (typeof e === "string") return fill(e, params);
  return fill(Number(params?.n) === 1 ? e.one : e.other, params);
}

export function setLang(l: Lang): void {
  try {
    localStorage.setItem(KEY, l);
  } catch {
    /* private mode */
  }
  location.reload();
}

document.cookie = `lacuna_lang=${lang}; path=/; max-age=31536000; samesite=strict`;
document.documentElement.lang = lang === "en" ? "en" : "zh-CN";
