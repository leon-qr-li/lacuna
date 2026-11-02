// 自定义快捷键 (decision 2026-11-02-custom-shortcuts): every customizable key in one table, the person's own keys
// (lacuna_app/routes/shortcuts.py keeps only the changed ones), and the one way handlers ask "is this key that
// action?". Mouse actions (Ctrl+wheel, Space+drag, right-click, dragging) and Esc are fixed and not listed here.
import { useEffect, useState } from "react";
import { t } from "../../i18n";
import { shortcutsApi } from "./api";

export type Group = "play" | "edit" | "any" | "review";
export type ActionId =
  | "play" | "back" | "fwd" | "find" | "cut" | "gap" | "undo" | "redo"
  | "rplay" | "prev" | "next" | "keep" | "restore" | "orig" | "edited" | "speed" | "help";

export interface Action {
  id: ActionId;
  group: Group;
  label: () => string;
  defaults: string[];
}

/** Keys are written "Mod+Shift+Z": Mod is Ctrl (⌘ on a Mac), then Alt, Shift, and one key name ("G", "Space",
 *  "ArrowLeft", "Delete", "?"). Delete also stands for Backspace. */
export const ACTIONS: Action[] = [
  { id: "play", group: "play", label: () => t("播放 / 暂停"), defaults: ["Space"] },
  { id: "back", group: "play", label: () => t("后退 5 秒"), defaults: ["ArrowLeft"] },
  { id: "fwd", group: "play", label: () => t("前进 5 秒"), defaults: ["ArrowRight"] },
  { id: "find", group: "play", label: () => t("搜索逐字稿"), defaults: ["Mod+F"] },
  { id: "cut", group: "edit", label: () => t("删掉选中的那一段"), defaults: ["Mod+X", "Delete"] },
  { id: "gap", group: "edit", label: () => t("在播放头加入间隙"), defaults: ["Shift+G"] },
  { id: "undo", group: "any", label: () => t("撤销"), defaults: ["Mod+Z"] },
  { id: "redo", group: "any", label: () => t("重做"), defaults: ["Mod+Shift+Z"] },
  { id: "rplay", group: "review", label: () => t("播放 / 暂停"), defaults: ["Space"] },
  { id: "prev", group: "review", label: () => t("上一处"), defaults: ["ArrowLeft", "J"] },
  { id: "next", group: "review", label: () => t("下一处"), defaults: ["ArrowRight"] },
  { id: "keep", group: "review", label: () => t("保留删除（恢复过的会重新删），跳到下一处"), defaults: ["K", "Y"] },
  { id: "restore", group: "review", label: () => t("恢复原话，跳到下一处"), defaults: ["R"] },
  { id: "orig", group: "review", label: () => t("听原始"), defaults: ["A"] },
  { id: "edited", group: "review", label: () => t("听剪后"), defaults: ["B"] },
  { id: "speed", group: "review", label: () => t("切换播放速度 1× / 1.25× / 1.5× / 2×"), defaults: ["S"] },
  { id: "help", group: "review", label: () => t("显示 / 隐藏这张快捷键表"), defaults: ["?"] },
];
const BY_ID = Object.fromEntries(ACTIONS.map((a) => [a.id, a])) as Record<ActionId, Action>;
export const actionOf = (id: ActionId) => BY_ID[id];

/** Which page a group's keys work on: two actions clash only when they share one. */
const PAGES: Record<Group, ("listen" | "review")[]> = { play: ["listen"], edit: ["listen"], any: ["listen", "review"], review: ["review"] };

/** Keys the browser keeps for itself (a page can't stop them) and keys that work buttons. */
const RESERVED = new Set([
  "Mod+W", "Mod+T", "Mod+N", "Mod+R", "Mod+L", "Mod+Q", "Mod+P", "Mod+H", "Mod+Tab",
  "Mod+Shift+T", "Mod+Shift+N", "Mod+Shift+W", "Mod+Shift+I", "Mod+Shift+J", "Mod+Shift+R", "Mod+Shift+Q",
  "F5", "F11", "F12", "Mod+F5", "Alt+F4",
]);
const BUTTON_KEYS = new Set(["Enter", "Tab", "Shift+Tab", "Escape"]);

export const isMac = () => /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);

/** The key as written in the table, or null for a modifier on its own (and keys typed into an IME). */
export function comboOf(e: Pick<KeyboardEvent, "key" | "code" | "ctrlKey" | "metaKey" | "altKey" | "shiftKey">): string | null {
  const k = e.key;
  if (!k || ["Control", "Meta", "Shift", "Alt", "AltGraph", "CapsLock", "Dead", "Process", "Unidentified", "OS", "Fn"].includes(k)) return null;
  let key: string;
  // letters and digits by their place on the keyboard, so Shift, Alt or another layout don't change them
  if (/^Key[A-Z]$/.test(e.code)) key = e.code.slice(3);
  else if (/^Digit[0-9]$/.test(e.code)) key = e.code.slice(5);
  else if (k === " ") key = "Space";
  else if (k === "Backspace") key = "Delete";
  else if (k.length === 1) key = k.toUpperCase();
  else key = k;
  const symbol = key.length === 1 && !/[A-Z0-9]/.test(key); // "?" already holds its Shift
  const mods: string[] = [];
  if (e.ctrlKey || e.metaKey) mods.push("Mod");
  if (e.altKey) mods.push("Alt");
  if (e.shiftKey && !symbol) mods.push("Shift");
  return [...mods, key].join("+");
}

/** "Ctrl+Shift+Z" / "⌘⇧Z", "空格", "←". */
export function keyLabel(combo: string): string {
  const mac = isMac();
  const NAMES: Record<string, string> = { Space: t("空格"), ArrowLeft: "←", ArrowRight: "→", ArrowUp: "↑", ArrowDown: "↓", Delete: "Delete", Escape: "Esc" };
  const parts = combo.split("+").map((p) =>
    p === "Mod" ? (mac ? "⌘" : "Ctrl") : p === "Shift" ? (mac ? "⇧" : "Shift") : p === "Alt" ? (mac ? "⌥" : "Alt") : NAMES[p] ?? p,
  );
  return parts.join(mac ? "" : "+");
}

// ---- the person's keys: only the changed ones, from the server; everything else is the default ----
let mine: Partial<Record<ActionId, string[]>> = {};
let loaded: Promise<void> | null = null;
const listeners = new Set<() => void>();
const changed = () => listeners.forEach((f) => f());

function load(): Promise<void> {
  loaded ??= shortcutsApi
    .get()
    .then((r) => {
      mine = cleanMine(r.keys);
      changed();
    })
    .catch(() => {
      loaded = null; // not signed in yet, or offline: defaults until the next try
    });
  return loaded;
}
function cleanMine(raw: Record<string, string[]>): Partial<Record<ActionId, string[]>> {
  const out: Partial<Record<ActionId, string[]>> = {};
  for (const [id, ks] of Object.entries(raw ?? {})) if (id in BY_ID && Array.isArray(ks)) out[id as ActionId] = ks.slice(0, 2);
  return out;
}

export const keysOf = (id: ActionId): string[] => mine[id] ?? BY_ID[id].defaults;
export const isChanged = (id: ActionId) => {
  const a = keysOf(id);
  const d = BY_ID[id].defaults;
  return a.length !== d.length || a.some((k, i) => k !== d[i]);
};
/** The first key of an action for help text ("Shift+G"), or "" when it has none. */
export const keyText = (id: ActionId) => (keysOf(id)[0] ? keyLabel(keysOf(id)[0]) : "");

/** Is this keydown one of the action's keys? */
export function matches(e: KeyboardEvent, id: ActionId): boolean {
  const c = comboOf(e);
  return !!c && keysOf(id).includes(c);
}
/** The first of these actions this keydown is a key of. */
export function hit<T extends ActionId>(e: KeyboardEvent, ids: readonly T[]): T | null {
  const c = comboOf(e);
  if (!c) return null;
  return ids.find((id) => keysOf(id).includes(c)) ?? null;
}

/** Re-render when the person's keys arrive or change; loads them on first use. */
export function useShortcuts(): number {
  const [n, setN] = useState(0);
  useEffect(() => {
    const on = () => setN((x) => x + 1);
    listeners.add(on);
    void load();
    return () => {
      listeners.delete(on);
    };
  }, []);
  return n;
}

export type Refusal = { kind: "reserved" | "button" } | { kind: "taken"; by: ActionId[] } | null;

/** Why a key can't simply be given to an action: the browser's, a button key, or another action on the same page. */
export function check(id: ActionId, combo: string): Refusal {
  if (BUTTON_KEYS.has(combo)) return { kind: "button" };
  if (RESERVED.has(combo)) return { kind: "reserved" };
  const pages = PAGES[BY_ID[id].group];
  const by = ACTIONS.filter((a) => a.id !== id && PAGES[a.group].some((p) => pages.includes(p)) && keysOf(a.id).includes(combo)).map((a) => a.id);
  return by.length ? { kind: "taken", by } : null;
}

/** Save the whole set (only what differs from the defaults is sent). Throws on failure, after putting back what was. */
export async function save(next: Partial<Record<ActionId, string[]>>): Promise<void> {
  const before = mine;
  const diff: Partial<Record<ActionId, string[]>> = {};
  for (const a of ACTIONS) {
    const ks = next[a.id] ?? a.defaults;
    if (ks.length !== a.defaults.length || ks.some((k, i) => k !== a.defaults[i])) diff[a.id] = ks;
  }
  mine = diff;
  changed();
  try {
    mine = cleanMine((await shortcutsApi.put(diff as Record<string, string[]>)).keys);
    changed();
  } catch (e) {
    mine = before;
    changed();
    throw e;
  }
}

/** Every action's keys now, to change and pass to save. */
export const snapshot = (): Partial<Record<ActionId, string[]>> => Object.fromEntries(ACTIONS.map((a) => [a.id, [...keysOf(a.id)]]));
