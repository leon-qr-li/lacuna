import { req } from "../../api";

/** An album's episode naming (lacuna_app/naming.py); null: titles stay as typed. */
export type Naming = { preset: Preset; before?: string; between?: string; after?: string };
export type Preset = "space" | "dot" | "bar" | "colon" | "issue" | "name" | "custom";
export type Rename = { id: string; before: string; after: string };

export const PRESETS: Exclude<Preset, "custom">[] = ["space", "dot", "bar", "colon", "issue", "name"];
const PARTS: Record<Exclude<Preset, "custom">, [string, string, string]> = {
  space: ["", " ", ""],
  dot: ["", " · ", ""],
  bar: ["", "｜", ""],
  colon: ["", "：", ""],
  issue: ["第{n}期", " ", ""], // episode titles stay Chinese // i18n-ignore
  name: ["", "", ""],
};
export const MAX_PART = 12;

const number = (id: string) => {
  const m = /(\d+)/.exec(id);
  return m ? String(Number(m[1])) : id;
};

/** The same as naming.title on the server: what an episode is called under `n`. */
export function formatTitle(n: Naming | null, id: string, name: string): string {
  const nm = name.split(/\s+/).filter(Boolean).join(" ");
  if (!n) return nm || id;
  const [b0, between, after] = n.preset === "custom" ? [n.before ?? "", n.between ?? "", n.after ?? ""] : PARTS[n.preset];
  if (n.preset === "name") return nm || id;
  const before = b0.replace("{n}", number(id));
  const num = b0.includes("{n}") ? before : before + id;
  if (!nm) return (num + after).trim() || id;
  return (num + between + nm + after).trim();
}

const SEPS = "[\\s·・|｜:：\\-–—_.,，、/]*";
const escape = (x: string) => x.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** The same as naming.bare on the server: the 名称 in a typed title ("EP012 · 奥本海默" -> "奥本海默"). */
export function bare(id: string, title: string, n: Naming | null = null): string {
  let s = title.split(/\s+/).filter(Boolean).join(" ");
  if (n) {
    const [b0, , after] = n.preset === "custom" ? [n.before ?? "", n.between ?? "", n.after ?? ""] : PARTS[n.preset];
    const b = b0.replace("{n}", number(id));
    if (b && s.startsWith(b)) s = s.slice(b.length);
    if (after && s.endsWith(after)) s = s.slice(0, -after.length);
  }
  s = s.replace(new RegExp(`^${escape(id)}${SEPS}`, "i"), "");
  s = s.replace(new RegExp(`^第\\s*0*${escape(number(id))}\\s*[期集]${SEPS}`), ""); // i18n-ignore
  if (n?.preset === "custom" && n.between && s.startsWith(n.between)) s = s.slice(n.between.length);
  return s.trim();
}

const base = (id: string) => `/api/albums/${encodeURIComponent(id)}/naming`;
const body = (n: Naming | null) => ({ preset: n?.preset ?? null, before: n?.before ?? "", between: n?.between ?? "", after: n?.after ?? "" });

export const namingApi = {
  set: (album: string, n: Naming | null) => req<{ naming: Naming | null }>("PUT", base(album), body(n)),
  preview: (album: string, n: Naming | null) => req<{ renames: Rename[] }>("POST", `${base(album)}/preview`, body(n)),
  apply: (album: string) => req<{ renamed: Rename[] }>("POST", `${base(album)}/apply`),
};
