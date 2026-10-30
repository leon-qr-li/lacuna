import { useCallback, useEffect, useState } from "react";
import { confirmDialog, noticeDialog } from "../dialog/Dialog";
import { t } from "../../i18n";
import { gapsApi } from "./api";
import type { Gap, GapsView } from "./api";

/** Sent after every change of an episode's gaps (detail: episode id): the timeline, the transcript and the
 *  「带配乐听」 player (library/useMusicListen) pick it up. */
export const GAPS_EVENT = "lacuna:gaps-changed";

/** The gaps of one episode, kept in step across the components that show them. `version`: the voice cut's
 *  version (a cut moves the gaps after it). */
export function useGaps(id: string, version: string) {
  const [gaps, setGaps] = useState<Gap[]>([]);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => {
    let live = true;
    gapsApi
      .list(id)
      .then((v) => live && setGaps(v.gaps))
      .catch(() => live && setGaps([]));
    return () => {
      live = false;
    };
  }, [id]);
  useEffect(() => load(), [load, version]);
  useEffect(() => {
    const on = (e: Event) => {
      const d = (e as CustomEvent<{ id: string; gaps: Gap[] }>).detail;
      if (d.id === id) setGaps(d.gaps);
    };
    window.addEventListener(GAPS_EVENT, on);
    return () => window.removeEventListener(GAPS_EVENT, on);
  }, [id]);

  const run = useCallback(
    async (p: Promise<GapsView>): Promise<GapsView | null> => {
      setBusy(true);
      try {
        const v = await p;
        window.dispatchEvent(new CustomEvent(GAPS_EVENT, { detail: { id, gaps: v.gaps } }));
        return v;
      } catch (e) {
        void noticeDialog((e as Error).message, t("间隙没改成"));
        return null;
      } finally {
        setBusy(false);
      }
    },
    [id],
  );
  const add = useCallback((at: number, len?: number) => run(gapsApi.add(id, at, len)), [run, id]);
  const setLen = useCallback((g: Gap, len: number) => run(gapsApi.setLen(id, g.id, len)), [run, id]);
  const remove = useCallback(
    async (g: Gap) => {
      if (g.filled_by && !(await confirmDialog({ message: t("间隙里的音乐「{name}」也会一起拿掉。", { name: g.music_name ?? "" }), danger: true, confirmLabel: t("删掉间隙") })))
        return null;
      return run(gapsApi.remove(id, g.id));
    },
    [run, id],
  );
  return { gaps, busy, add, setLen, remove };
}

export type Gaps = ReturnType<typeof useGaps>;

/** Before an export (Leon 2026-10-30): gaps still without music are exported as silence; say so first.
 *  true = go ahead. A failed check doesn't stop the export. */
export async function confirmEmptyGaps(id: string): Promise<boolean> {
  let n = 0;
  try {
    n = (await gapsApi.list(id)).gaps.filter((g) => !g.filled_by).length;
  } catch {
    return true;
  }
  if (!n) return true;
  return confirmDialog({
    title: t("还有间隙没配乐"),
    message: t("这一集有 {n} 个间隙还没配乐，导出时会是静音。可以先到「配乐」点「给间隙自动配乐」。", { n }),
    confirmLabel: t("按静音导出"),
    cancelLabel: t("先不导出"),
  });
}
