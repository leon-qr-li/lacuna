import type { ReactNode } from "react";
import type { EpisodeListItem } from "../../api";
import { fmt } from "../../api";
import { t } from "../../i18n";
import { useProjects } from "../projects/api";

/** One episode tile (剧集 and 已归档 share it); `actions` sit in the tile's corner. The tile shows the chosen
 *  cover, else the show's colour, and a stripe on top for where the episode is (batch 7, T3). */
export function EpisodeCard({ e, href, actions, extra }: { e: EpisodeListItem; href?: string; actions?: ReactNode; extra?: ReactNode }) {
  const color = useProjects()?.current?.color;
  const stage = e.error ? "error" : e.pending_review ? "review" : e.exported ? "exported" : "reviewed";
  const body = (
    <>
      <span className={`ep-stripe ep-stripe-${stage}`} aria-hidden="true" data-testid="episode-stripe" data-stage={stage} />
      {e.poster ? (
        <img className="ep-cover ep-cover-img" src={e.poster} alt="" data-testid="episode-poster" />
      ) : (
        <span className="ep-cover" aria-hidden="true" style={color ? { background: color } : undefined}>
          {e.title.replace(/^[^\p{L}\p{N}]+/u, "").slice(0, 1)}
        </span>
      )}
      <span className="ep-body">
        <strong>{e.title}</strong>
        {e.error ? (
          <span className="error small">
            {t("无法打开：")}
            {e.error}
          </span>
        ) : (
          <>
            <span className="muted small mono">
              {fmt(e.raw_duration ?? 0)} → {fmt(e.duration ?? 0)}
              {e.demo && t(" · 演示数据")}
            </span>
            <span className={`chip ${e.pending_review ? "chip-warn" : "chip-ok"}`}>
              {e.pending_review ? t("{n} 处待审阅", { n: e.pending_review }) : e.exported ? t("已导出") : t("都审阅完了")}
            </span>
          </>
        )}
        {extra}
      </span>
    </>
  );
  return (
    <li className="ep-item" data-testid="episode" data-id={e.id}>
      {href ? <a href={href}>{body}</a> : <div className="ep-tile">{body}</div>}
      {actions && <div className="ep-actions">{actions}</div>}
    </li>
  );
}
