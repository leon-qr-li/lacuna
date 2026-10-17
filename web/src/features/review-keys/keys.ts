/**
 * Review-page shortcuts, one table for the key handler and the "?" help card.
 * Space play / pause, ← → previous / next, K keep, R restore, A / B original / cut.
 * J and Y are kept as quiet aliases for people used to the first version.
 */
import { t } from "../../i18n";

export type ReviewAction = "prev" | "next" | "toggle" | "a" | "b" | "keep" | "restore" | "help";

const MAP: Record<string, ReviewAction> = {
  arrowleft: "prev",
  arrowright: "next",
  j: "prev",
  " ": "toggle",
  a: "a",
  b: "b",
  k: "keep",
  y: "keep",
  r: "restore",
  "?": "help",
};

/** Actions that change the episode or start playback: never fire on key auto-repeat. */
const ONCE = new Set<ReviewAction>(["keep", "restore", "toggle", "help"]);

/** The action for a keydown on the review page, or null when it is not ours (typing, modifiers, repeat). */
export function reviewAction(e: Pick<KeyboardEvent, "key" | "target" | "metaKey" | "ctrlKey" | "altKey" | "repeat">): ReviewAction | null {
  const el = e.target as HTMLElement | null;
  const tag = el?.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el?.isContentEditable) return null;
  if (e.metaKey || e.ctrlKey || e.altKey) return null;
  const a = MAP[e.key.toLowerCase()] ?? null;
  if (a && e.repeat && ONCE.has(a)) return null;
  return a;
}

/** Rows of the help card: keys shown, what they do. */
export const help = (): { keys: string[]; label: string }[] => [
  { keys: [t("空格")], label: t("播放 / 暂停") },
  { keys: ["←", "→"], label: t("上一处 / 下一处") },
  { keys: ["K"], label: t("保留（保持现状），跳到下一处") },
  { keys: ["R"], label: t("恢复原话，跳到下一处") },
  { keys: ["A", "B"], label: t("切换原始 / 剪后") },
  { keys: ["?"], label: t("显示 / 隐藏这张快捷键表") },
];
