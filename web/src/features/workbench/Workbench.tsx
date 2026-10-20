import type { ReactNode } from "react";
import type { EditInfo, Episode } from "../../api";
import { fmt, statusLabel } from "../../api";
import { Icon } from "../../components/Icon";
import { t } from "../../i18n";
import "./workbench.css";

/** 整集试听 as one screen (Leon 2026-10-20, version B): the editing timeline on top with the whole-episode minimap
 * and the player inside it, the transcript under it, and a side panel with two tabs (AI 制作人 / 这附近改了什么).
 * Each part scrolls inside itself, so editing never means scrolling the page up and down. */

export type SideTab = "ai" | "near";
const TAB_KEY = "lacuna.side.tab";

export function readSideTab(): SideTab {
  try {
    return localStorage.getItem(TAB_KEY) === "near" ? "near" : "ai";
  } catch {
    return "ai";
  }
}
export function writeSideTab(v: SideTab) {
  try {
    localStorage.setItem(TAB_KEY, v);
  } catch {
    /* private mode */
  }
}

/** The side panel's tabs, in the AI 制作人 panel's header (the 收起 button stays at its right). */
export function SideTabs({ tab, onTab, near, badge }: { tab: SideTab; onTab: (v: SideTab) => void; near: number; badge: ReactNode }) {
  return (
    <div className="side-tabs" role="tablist" aria-label={t("侧栏")}>
      <button type="button" role="tab" className="side-tab" aria-selected={tab === "ai"} onClick={() => onTab("ai")} data-testid="tab-ai">
        {t("AI 制作人")} {badge}
      </button>
      <button type="button" role="tab" className="side-tab" aria-selected={tab === "near"} onClick={() => onTab("near")} data-testid="tab-near">
        {t("这附近改了什么")}
        {near > 0 && <span className="side-n">{near}</span>}
      </button>
    </div>
  );
}

/** The whole episode in one thin strip above the ruler: topics (when there are), edit ticks, the playhead. */
export function Minimap({ ep, time, onSeek }: { ep: Episode; time: number; onSeek: (t: number) => void }) {
  const d = ep.duration || 1;
  const pct = (s: number) => `${(100 * s) / d}%`;
  const jump = (e: React.MouseEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    onSeek(((e.clientX - r.left) / r.width) * d);
  };
  return (
    <div className="wb-mini" aria-label={ep.topics.length ? t("话题段落") : t("整集概览")} role="group">
      {ep.topics.length > 0 && (
        <div className="wb-topics">
          {ep.topics.map((tp) => (
            <button key={tp.start} type="button" className="topic" style={{ flexGrow: Math.max(tp.end - tp.start, 1) }} onClick={() => onSeek(tp.start)} title={tp.title}>
              {tp.title}
            </button>
          ))}
        </div>
      )}
      <div className="overview wb-ov" onClick={jump} role="presentation" title={t("深色刻度 = 需要你过目的改动 · 点击跳转")} data-testid="minimap">
        {ep.edits
          .filter((e) => e.category !== "loudness")
          .map((e) => (
            <span key={e.id} className={`tick ${e.consequential ? "major" : ""} ${e.status === "restored" ? "restored" : ""}`} style={{ left: pct(e.t) }} />
          ))}
        <span className="ov-head" style={{ left: pct(time) }} />
      </div>
    </div>
  );
}

/** The card for an edit under the pointer on the timeline: what it is, hear around it, restore / re-apply. */
export function CutPop({ e, onListen, onReview }: { e: EditInfo; onListen: () => void; onReview: (e: EditInfo, action: "restore" | "apply") => void }) {
  return (
    <>
      <div className="wb-pop-title">{e.title}</div>
      <div className={`wb-pop-meta small ${e.consequential && !e.approved ? "warn" : "muted"}`}>
        <span className="mono">{fmt(e.t)}</span> · {statusLabel(e)}
      </div>
      <div className="wb-pop-row">
        <button type="button" className="btn btn-ghost btn-small" onClick={onListen}>
          ▶ {t("听前后")}
        </button>
        {e.status === "applied" ? (
          <button type="button" className="btn btn-small" onClick={() => onReview(e, "restore")}>
            {t("恢复")}
          </button>
        ) : (
          <button type="button" className="btn btn-small" onClick={() => onReview(e, "apply")}>
            {t("重新应用")}
          </button>
        )}
      </div>
    </>
  );
}

/** 「下一步」 at the top right of every step, next to 撤销 / 重做 / 导出 (Leon 2026-10-20: global, not at the page bottom). */
export function NextStep({ href, label }: { href: string; label: string }) {
  return (
    <a className="btn btn-small linkbtn wb-next" href={href} title={t("这一步做完了？")} data-testid="next-step">
      {t("下一步：")}
      {label} <Icon name="chev" />
    </a>
  );
}
