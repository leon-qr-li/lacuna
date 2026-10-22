// 导出 page, right side: what this episode became (length, what was cut, music, the two voices).
import { useEffect, useState } from "react";
import type { Episode } from "../../api";
import { fmt } from "../../api";
import { t } from "../../i18n";
import { libraryApi } from "../library/api";
import type { MusicView } from "../library/api";
import { levelsApi } from "../levels/api";
import type { Levels } from "../levels/api";

export function EpisodeSummary({ id, ep }: { id: string; ep: Episode }) {
  const [m, setM] = useState<MusicView | null>(null);
  const [lv, setLv] = useState<Levels | null>(null);
  useEffect(() => {
    libraryApi.music(id).then(setM, () => setM(null));
    levelsApi.levels(id).then(setLv, () => setLv(null));
  }, [id, ep.version]);
  const final = m?.duration ?? ep.duration;
  const cut = Math.max(ep.raw_duration - ep.duration, 0);
  const pieces = m?.placements.filter((p) => !p.missing) ?? [];
  const names = [...new Set(pieces.map((p) => p.role_label))].join(" · ");
  const spread = lv ? Math.max(...lv.tracks.map((x) => x.level_lufs ?? -99)) - Math.min(...lv.tracks.map((x) => x.level_lufs ?? -99)) : 0;
  return (
    <div className="card xsum" data-testid="export-summary" data-tour="export-summary">
      <b>{t("这一集")}</b>
      <div className="xsum-grid">
        <div>
          <span className="small muted">{t("时长")}</span>
          <b data-testid="export-summary-length">
            {fmt(ep.raw_duration)} → {fmt(final)}
          </b>
          <span className="small muted">{pieces.length ? t("含配乐") : t("不含配乐")}</span>
        </div>
        <div>
          <span className="small muted">{t("剪掉")}</span>
          <b>{t("{n} 秒", { n: Math.round(cut) })}</b>
          <span className="small muted">{t("原始 {d}", { d: fmt(ep.raw_duration) })}</span>
        </div>
        <div>
          <span className="small muted">{t("配乐")}</span>
          <b>{t("{n} 处", { n: pieces.length })}</b>
          <span className="small muted">{names || t("没有配乐")}</span>
        </div>
        <div>
          <span className="small muted">{ep.tracks.length > 1 ? t("几位主持人的音量") : t("音量")}</span>
          {lv == null ? (
            <b>—</b>
          ) : lv.even || ep.tracks.length < 2 ? (
            <b className="ok">{t("已统一")}</b>
          ) : (
            <b className="warn">{t("相差 {d} dB", { d: spread.toFixed(1) })}</b>
          )}
          <span className="small muted">{t("导出后 −16 LUFS")}</span>
        </div>
      </div>
    </div>
  );
}
