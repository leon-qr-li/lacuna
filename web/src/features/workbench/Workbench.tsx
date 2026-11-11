import type { ReactNode } from "react";
import type { EditInfo } from "../../api";
import { fmt, statusLabel } from "../../api";
import { Icon } from "../../components/Icon";
import { t } from "../../i18n";
import { useListenOnly } from "../listen-only/state";
import "./workbench.css";

/** 整集试听 as one screen (Leon 2026-10-20, version B): the editing timeline on top with the player inside it
 * (no minimap: Leon's round 4), the transcript under it, and a side panel with two tabs (AI 制作人 / 这附近改了什么).
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
        {t("LACUNA")} {badge}
      </button>
      <button type="button" role="tab" className="side-tab" aria-selected={tab === "near"} onClick={() => onTab("near")} data-testid="tab-near">
        {t("这附近改了什么")}
        {near > 0 && <span className="side-n">{near}</span>}
      </button>
    </div>
  );
}

/** The card for an edit under the pointer on the timeline: what it is, hear around it, restore / re-apply. */
export function CutPop({ e, onListen, onReview }: { e: EditInfo; onListen: () => void; onReview: (e: EditInfo, action: "restore" | "apply") => void }) {
  const ro = useListenOnly();
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
          <button type="button" className="btn btn-small" disabled={ro} onClick={() => onReview(e, "restore")}>
            {t("恢复")}
          </button>
        ) : (
          <button type="button" className="btn btn-small" disabled={ro} onClick={() => onReview(e, "apply")}>
            {t("重新应用")}
          </button>
        )}
      </div>
    </>
  );
}

/** 「下一步」 at the top right of every step, next to the 「第一刀已完成」 pill (Leon 2026-10-20: global, not at the page bottom). */
export function NextStep({ href, label }: { href: string; label: string }) {
  return (
    <a className="btn btn-small linkbtn wb-next" href={href} title={t("这一步做完了？")} data-testid="next-step">
      {t("下一步：")}
      {label} <Icon name="chev" />
    </a>
  );
}
