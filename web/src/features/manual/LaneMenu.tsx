import { forwardRef } from "react";
import type { Episode } from "../../api";
import { t } from "../../i18n";
import type { Manual } from "./useManual";

const svg = (path: JSX.Element) => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    {path}
  </svg>
);
const CUT = svg(
  <>
    <circle cx="6" cy="6" r="3" />
    <circle cx="6" cy="18" r="3" />
    <path d="M20 4L8.1 15.9M14.5 14.5L20 20M8.1 8.1L12 12" />
  </>,
);
const MUTE = svg(
  <>
    <path d="M4 9v6h4l5 4V5L8 9H4z" />
    <path d="M17 9l4 6M21 9l-4 6" />
  </>,
);

/**
 * What to do with a stretch selected on the timeline (Leon 2026-10-20, round 4): a small vertical menu like a
 * right-click menu, at the selection's right edge between the tracks: 删掉这段 (Ctrl X), then 只静音 <host> per
 * host. No time text and no 听选中 / 取消 (Space plays the selection, Esc drops it). Placed by EditLanes.
 */
export const LaneMenu = forwardRef<HTMLDivElement, { ep: Episode; m: Manual; left: number; top: number; hidden: boolean }>(
  function LaneMenu({ ep, m, left, top, hidden }, ref) {
    const { busy } = m;
    return (
      <div
        ref={ref}
        className="ml-menu"
        role="menu"
        aria-label={t("选中的这一段")}
        style={{ left, top, visibility: hidden ? "hidden" : undefined }}
        data-testid="ml-menu"
        onPointerDown={(e) => e.stopPropagation()}
        onContextMenu={(e) => e.preventDefault()}
      >
        <button type="button" role="menuitem" className="ml-menu-item" disabled={busy} onClick={() => void m.cut(null)} data-testid="ml-cut">
          {CUT}
          <span>{t("删掉这段")}</span>
          <kbd>Ctrl X</kbd>
        </button>
        <div className="ml-menu-sep" role="separator" />
        {ep.tracks.map((tr) => (
          <button
            key={tr.name}
            type="button"
            role="menuitem"
            className="ml-menu-item"
            disabled={busy}
            onClick={() => void m.cut(tr.name)}
            data-testid={`ml-mute-${tr.name}`}
          >
            {MUTE}
            <span>{t("只静音 {name}", { name: tr.name })}</span>
          </button>
        ))}
      </div>
    );
  },
);
