import { forwardRef, useState } from "react";
import { t } from "../../i18n";
import { useListenOnly } from "../listen-only/state";
import { DEFAULT_LEN, LENGTHS } from "./api";
import type { Gap } from "./api";
import type { Gaps } from "./useGaps";
import "./gaps.css";

const PAUSE = (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
    <path d="M9 6v12M15 6v12" />
  </svg>
);

/** 「间隙 15 秒」 and what plays in it */
export const gapLabel = (g: Gap) => t("间隙 {s} 秒", { s: g.len_s });
const gapState = (g: Gap) => (g.filled_by ? `♪ ${g.music_name ?? ""}` : t("待配乐"));

/** Length chips (5 / 10 / 15 / 30 s) and a box for any other length. */
function Lengths({ value, disabled, onPick, testid }: { value: number | null; disabled: boolean; onPick: (s: number) => void; testid: string }) {
  const [custom, setCustom] = useState("");
  const other = () => {
    const v = Number(custom.replace(",", "."));
    if (Number.isFinite(v) && v >= 1 && v <= 300) {
      onPick(Math.round(v * 10) / 10);
      setCustom("");
    }
  };
  return (
    <span className="gap-lens" role="group" aria-label={t("间隙长度")}>
      {LENGTHS.map((s) => (
        <button key={s} type="button" className={`gap-len ${value === s ? "is-on" : ""}`} disabled={disabled} onClick={() => onPick(s)} data-testid={`${testid}-${s}`}>
          {t("{s} 秒", { s })}
        </button>
      ))}
      <input
        className="gap-len-input mono"
        inputMode="decimal"
        placeholder={t("其他")}
        aria-label={t("其他长度（秒）")}
        value={custom}
        disabled={disabled}
        onChange={(e) => setCustom(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && other()}
        onBlur={other}
        data-testid={`${testid}-custom`}
      />
    </span>
  );
}

/** The card of one gap: its length, what plays in it, 删掉. */
export function GapCard({ g, gaps, onDone }: { g: Gap; gaps: Gaps; onDone?: () => void }) {
  const ro = useListenOnly();
  return (
    <div className="gap-card" data-testid="gap-card">
      <div className="gap-card-head">
        {PAUSE}
        <b>{gapLabel(g)}</b>
        <span className={`gap-state ${g.filled_by ? "is-filled" : ""}`}>{gapState(g)}</span>
      </div>
      <Lengths value={g.len_s} disabled={gaps.busy || ro} onPick={(s) => void gaps.setLen(g, s)} testid="gap-set" />
      <p className="small muted gap-card-note">
        {g.filled_by ? t("音乐在间隙里淡入淡出，间隙长度不变。") : t("整集试听勾「带配乐听」能听到间隙；到「配乐」可以给间隙自动配乐。")}
      </p>
      <button
        type="button"
        className="btn btn-outline btn-small gap-del"
        disabled={gaps.busy || ro}
        onClick={async () => {
          if (await gaps.remove(g)) onDone?.();
        }}
        data-testid="gap-delete"
      >
        {t("删掉间隙")}
      </button>
    </div>
  );
}

/** The timeline's right-click menu away from a selection: 「在此处加入间隙」, 15 s or another length. */
export const GapAddMenu = forwardRef<HTMLDivElement, { left: number; top: number; gaps: Gaps; at: number; onClose: () => void }>(
  function GapAddMenu({ left, top, gaps, at, onClose }, ref) {
    const ro = useListenOnly();
    const add = async (len: number) => {
      onClose();
      await gaps.add(at, len);
    };
    return (
      <div
        ref={ref}
        className="ml-menu gap-menu"
        role="menu"
        aria-label={t("在此处加入间隙")}
        style={{ left, top }}
        data-testid="gap-menu"
        onPointerDown={(e) => e.stopPropagation()}
        onContextMenu={(e) => e.preventDefault()}
      >
        <button type="button" role="menuitem" className="ml-menu-item" disabled={gaps.busy || ro} onClick={() => void add(DEFAULT_LEN)} data-testid="gap-add">
          {PAUSE}
          <span>{t("在此处加入间隙")}</span>
          <kbd>G</kbd>
        </button>
        <Lengths value={DEFAULT_LEN} disabled={gaps.busy || ro} onPick={(s) => void add(s)} testid="gap-add" />
        <p className="small muted gap-menu-note">{t("会放到最近的两句话之间")}</p>
      </div>
    );
  },
);

/** A gap on one host's lane of the timeline: a striped mark at its point (the voice cut has no room in it; the time
 *  opens in the final mix). The first lane carries the label. */
export function GapMark({ g, left, label, onOpen }: { g: Gap; left: string; label: boolean; onOpen: (g: Gap, el: HTMLElement) => void }) {
  return (
    <button
      type="button"
      className={`gap-mark ${g.filled_by ? "is-filled" : ""}`}
      style={{ left }}
      title={`${gapLabel(g)} · ${gapState(g)}`}
      aria-label={`${gapLabel(g)} · ${gapState(g)}`}
      onPointerDown={(e) => e.stopPropagation()}
      onClick={(e) => onOpen(g, e.currentTarget)}
      data-testid="gap-mark"
      data-at={g.voice_s.toFixed(2)}
    >
      {label && <span className="gap-mark-cap">{t("{s} 秒", { s: g.len_s })}</span>}
    </button>
  );
}

/** Between two lines of the transcript: an existing gap's row, else a 「＋」 that shows on hover. */
export function TranscriptGap({ here, gaps, at }: { here: Gap[]; gaps: Gaps; at: number }) {
  const ro = useListenOnly();
  const [open, setOpen] = useState<string | null>(null);
  if (here.length)
    return (
      <>
        {here.map((g) => (
          <div key={g.id} className="gap-row" data-testid="gap-row">
            <span className="gap-row-main">
              {PAUSE}
              <b>{gapLabel(g)}</b>
              <span className={`gap-state ${g.filled_by ? "is-filled" : ""}`}>{gapState(g)}</span>
            </span>
            <button type="button" className="gap-link" onClick={() => setOpen(open === g.id ? null : g.id)} data-testid="gap-row-edit">
              {open === g.id ? t("收起") : t("改长度 / 删掉")}
            </button>
            {open === g.id && <GapCard g={g} gaps={gaps} onDone={() => setOpen(null)} />}
          </div>
        ))}
      </>
    );
  if (ro) return null;
  return (
    <div className="gap-plus">
      <button type="button" className="gap-plus-btn" disabled={gaps.busy} onClick={() => void gaps.add(at)} title={t("在这两句之间加入 {s} 秒间隙", { s: DEFAULT_LEN })} data-testid="gap-plus">
        <span className="gap-plus-dot" aria-hidden>
          ＋
        </span>
        <span className="gap-plus-text">{t("在这里加入间隙")}</span>
      </button>
    </div>
  );
}

/** 配乐 page: how many gaps the episode has, and 「给间隙自动配乐」 for the ones without music. */
export function GapBanner({ list, onFill }: { list: Gap[] | undefined; onFill: () => void }) {
  const ro = useListenOnly();
  const empty = list?.filter((g) => !g.filled_by).length ?? 0;
  if (!empty) return null; // every gap has its music: nothing to ask
  return (
    <div className="card banner-card gap-banner" data-testid="gap-banner">
      <span className="grow">{t("这一集有 {n} 个间隙，{m} 个还没配乐。", { n: list!.length, m: empty })}</span>
      <button type="button" className="btn btn-primary btn-small" disabled={ro} onClick={onFill} data-testid="gap-fill" title={t("先用你放进来的间奏，再从素材库里用途是「休息间隙」的音乐挑，按从左到右填进空着的间隙。先给建议，试听后再采用。")}>
        {t("给间隙自动配乐")}
      </button>
    </div>
  );
}

/** Gaps without music on the 配乐 page's strip (filled ones show as their interlude). */
export function StripGaps({ list, total }: { list: Gap[] | undefined; total: number }) {
  return (
    <>
      {(list ?? [])
        .filter((g) => !g.filled_by)
        .map((g) => (
          <span
            key={g.id}
            className="mstrip-gap"
            style={{ left: `${(100 * g.final_s) / total}%`, width: `${(100 * g.len_s) / total}%` }}
            title={`${gapLabel(g)} · ${t("待配乐")}`}
            data-testid="mstrip-gap"
          />
        ))}
    </>
  );
}
