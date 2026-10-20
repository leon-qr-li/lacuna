import { useState } from "react";
import type { Episode } from "../../api";
import { t } from "../../i18n";
import { transcriptFixApi } from "./api";
import type { Proofread } from "./api";
import "./transcript-fix.css";

/**
 * 校对专有名词 (decision transcript-terms): a chip on 文字稿剪辑 that proofreads the transcript again against the
 * show's names (project settings, albums, names corrected before). New imports already get this; the chip is
 * for episodes imported before, or after new terms were added. Only the words' text changes.
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
  if (!ep.has_transcript) return null;
  const go = async () => {
    setBusy(true);
    await run(transcriptFixApi.fix(ep.id, time), (next) => {
      const r = next as Proofread;
      if (r.changed > 0) {
        const list = r.fixes
          .slice(0, 4)
          .map((f) => t("{wrong} → {right}（{count} 处）", { wrong: f.wrong, right: f.right, count: f.count }))
          .join(t("、"));
        return t("已校对 {n} 处：{list}", { n: r.changed, list });
      }
      return r.ai ? t("没有找到听错的专有名词") : t("LACUNA 没连上，只按以前改过的名字校对了，没有找到要改的");
    });
    setBusy(false);
  };
  return (
    <button
      type="button"
      className="tf-chip"
      disabled={busy}
      onClick={() => void go()}
      data-testid="term-fix-btn"
      title={t("按项目设置里的节目名、主播名、专辑名等，重新校对文字稿里听错的专有名词（只改文字，不动音频和剪辑）")}
    >
      {busy ? t("正在校对…") : t("校对专有名词")}
    </button>
  );
}
