import type { ReactNode } from "react";
import type { EpisodeListItem } from "../../api";
import { fmt } from "../../api";
import { t } from "../../i18n";

/** One episode tile (剧集 and 已归档 share it); `actions` sit in the tile's corner. */
export function EpisodeCard({ e, href, actions, extra }: { e: EpisodeListItem; href?: string; actions?: ReactNode; extra?: ReactNode }) {
  const body = (
    <>
      <span className="ep-cover" aria-hidden="true">
        {e.title.replace(/^[^\p{L}\p{N}]+/u, "").slice(0, 1)}
      </span>
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
              {e.pending_review ? t("{n} 处待过目", { n: e.pending_review }) : t("都过目了")}
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
