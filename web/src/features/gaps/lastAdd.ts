// Undo for 「加入间隙」 (Leon 2026-11-02, a user kept adding gaps by mistake): gaps live outside the episode's
// undo history, so the gap added last is remembered here. Ctrl+Z and the toast's 撤销 take it back first; any
// later change of the episode (App's run) or of that gap forgets it, so Ctrl+Z then undoes that change as before.
import { gapsApi } from "./api";
import { GAPS_EVENT } from "./useGaps";

/** Sent after a gap is added (detail: episode id, length): the episode page shows 「已加入…」 with 撤销. */
export const GAP_ADDED_EVENT = "lacuna:gap-added";

let last: { ep: string; gap: string } | null = null;

export function noteAdded(ep: string, gap: string, len: number) {
  last = { ep, gap };
  window.dispatchEvent(new CustomEvent(GAP_ADDED_EVENT, { detail: { id: ep, len } }));
}

/** Forget the remembered gap: a newer change happened (all of them, or only when it is this gap). */
export function forgetAdded(gap?: string) {
  if (!gap || last?.gap === gap) last = null;
}

export const canUndoAdded = (ep: string) => last?.ep === ep;

/** Take back the gap added last in this episode. true when there was one (whatever the server said). */
export async function undoAdded(ep: string): Promise<boolean> {
  if (last?.ep !== ep) return false;
  const gap = last.gap;
  last = null;
  try {
    const v = await gapsApi.remove(ep, gap);
    window.dispatchEvent(new CustomEvent(GAPS_EVENT, { detail: { id: ep, gaps: v.gaps } }));
  } catch {
    /* already gone (removed by hand or by someone else): nothing left to undo */
  }
  return true;
}
