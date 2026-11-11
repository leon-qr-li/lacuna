/**
 * Review-page shortcuts, one table for the key handler and the "?" help card. The keys are the person's own
 * (设置 → 快捷键, features/shortcuts/keys.ts); defaults: Space play / pause, ← → previous / next (J also
 * previous), K keep (Y too), R restore, A / B original / cut, S speed, ? this card.
 */
import { t } from "../../i18n";
import type { ActionId } from "../shortcuts/keys";
import { hit, keyLabel, keysOf } from "../shortcuts/keys";

export type ReviewAction = "prev" | "next" | "toggle" | "a" | "b" | "keep" | "restore" | "speed" | "help";

const OF: Record<ReviewAction, ActionId> = {
  prev: "prev",
  next: "next",
  toggle: "rplay",
  a: "orig",
  b: "edited",
  keep: "keep",
  restore: "restore",
  speed: "speed",
  help: "help",
};
const IDS = Object.values(OF);
const BACK = Object.fromEntries(Object.entries(OF).map(([r, id]) => [id, r])) as Record<ActionId, ReviewAction>;

/** Actions that change the episode or start playback: never fire on key auto-repeat. */
const ONCE = new Set<ReviewAction>(["keep", "restore", "toggle", "speed", "help"]);

/** The action for a keydown on the review page, or null when it is not ours (typing, other keys, repeat). */
export function reviewAction(e: KeyboardEvent): ReviewAction | null {
  const el = e.target as HTMLElement | null;
  const tag = el?.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el?.isContentEditable) return null;
  const id = hit(e, IDS);
  const a = id ? BACK[id] : null;
  if (a && e.repeat && ONCE.has(a)) return null;
  return a;
}

/** The first key of an action (the others are quiet extras, like J and Y by default). */
const keys = (r: ReviewAction) => keysOf(OF[r]).slice(0, 1).map(keyLabel);

/** Rows of the help card: keys shown, what they do. An action without a key shows 未设置. */
export const help = (): { keys: string[]; label: string }[] =>
  [
    { keys: keys("toggle"), label: t("播放 / 暂停") },
    { keys: [...keys("prev"), ...keys("next")], label: t("上一处 / 下一处") },
    { keys: keys("keep"), label: t("保留删除（恢复过的会重新删），跳到下一处") },
    { keys: keys("restore"), label: t("恢复原话，跳到下一处") },
    { keys: [...keys("a"), ...keys("b")], label: t("切换原始 / 剪后") },
    { keys: keys("speed"), label: t("切换播放速度 1× / 1.25× / 1.5× / 2×") },
    { keys: keys("help"), label: t("显示 / 隐藏这张快捷键表") },
  ].map((r) => ({ ...r, keys: r.keys.length ? r.keys : [t("未设置")] }));
