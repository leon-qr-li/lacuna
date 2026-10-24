// Opening the 反馈 panel from anywhere: the top-bar button, 「告诉我们」 on an error, the 自动发布 card.
import type { Kind } from "./api";

export interface Prefill {
  kind?: Kind;
  source?: "button" | "error" | "publish";
  /** an error: its title and what it said (shown as 已帮你填好, attached) */
  error?: { title: string; message?: string; code?: string };
  /** from 节目设置 → 自动发布: the platforms ticked */
  platforms?: string[];
  /** open on 我的反馈 */
  mine?: boolean;
}

const EVENT = "lacuna:feedback";

export function openFeedback(p: Prefill = {}) {
  window.dispatchEvent(new CustomEvent<Prefill>(EVENT, { detail: p }));
}

export function onOpenFeedback(fn: (p: Prefill) => void) {
  const h = (e: Event) => fn((e as CustomEvent<Prefill>).detail ?? {});
  window.addEventListener(EVENT, h);
  return () => window.removeEventListener(EVENT, h);
}
