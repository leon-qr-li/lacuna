import { useEffect, useRef, useState } from "react";
import type { Episode } from "../../api";
import { t } from "../../i18n";
import { transcriptFixApi } from "./api";
import "./transcript-fix.css";

/**
 * 专有名词自动校对 (decision transcript-terms): when an episode opens whose transcript was never proofread with the
 * current terms (imported before, or the project / system terms changed since), it is proofread right away, by
 * itself; a chip says so while it runs and a notice lists what changed. New imports are already proofread.
 */
export function TermFixButton({
  ep,
  time,
  run,
}: {
  ep: Episode;
  time: number;
  run: (p: Promise<Episode>, msg?: string | ((next: Episode) => string)) => Promise<boolean>;
}) {
  const [busy, setBusy] = useState(false);
  const at = useRef(time);
  at.current = time;

  useEffect(() => {
    if (!ep.has_transcript) return;
    let live = true;
    transcriptFixApi
      .due(ep.id)
      .then(async (d) => {
        if (!live || !d.due) return;
        setBusy(true);
        // a failure stays quiet (asked again next time the episode opens); the result replaces the episode
        const r = await transcriptFixApi.fix(ep.id, at.current).catch(() => null);
        if (r && live) {
          const list = r.fixes
            .slice(0, 4)
            .map((f) => t("{wrong} → {right}（{count} 处）", { wrong: f.wrong, right: f.right, count: f.count }))
            .join(t("、"));
          await run(Promise.resolve(r), r.changed ? t("已按专有名词自动校对 {n} 处：{list}", { n: r.changed, list }) : undefined);
        }
        if (live) setBusy(false);
      })
      .catch(() => live && setBusy(false));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ep.id, ep.has_transcript]);

  if (!busy) return null;
  return (
    <span className="tf-chip" role="status" data-testid="term-fix-busy"
      title={t("按节目设置和系统专有名词校对文字稿里听错的名字（只改文字，不动音频和剪辑）")}>
      {t("正在校对专有名词…")}
    </span>
  );
}
