import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { t } from "../../i18n";
import { subscribe } from "./activity";
import "./loading.css";

/**
 * The one loading language of the app (decision 2026-10-17-unified-loading):
 * - a page or tab whose data is on its way shows `PageLoading` at once: the wave, a line saying what
 *   is opening, and grey shapes of what will appear (never a blank page, however short the wait);
 * - an action that takes seconds shows `Wave` where it happens (in the button, or a `Waiting` row);
 * - a long job shows `JobProgress`: steps, a bar, time used and an estimate of what is left;
 * - every request the person started also moves a thin line under the top bar (`TopLine`).
 */

/** The animated sound-wave mark. Decorative: the text next to it says what is happening. */
export function Wave({ size = "sm", className = "" }: { size?: "sm" | "lg"; className?: string }) {
  return (
    <span className={`ld-wave ld-wave-${size} ${className}`} aria-hidden="true">
      <i />
      <i />
      <i />
      <i />
      <i />
    </span>
  );
}

/** A grey placeholder block with a moving sheen. */
export function Skel({ w, h = 12, r, style }: { w?: number | string; h?: number | string; r?: number; style?: CSSProperties }) {
  return <span className="ld-skel" aria-hidden="true" style={{ width: w, height: h, borderRadius: r, ...style }} />;
}

/** Placeholder rows shaped like the episode cards on the home page. */
export function EpisodeListSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <ul className="ld-ep-list" aria-hidden="true" data-testid="episodes-loading">
      {Array.from({ length: rows }, (_, i) => (
        <li key={i}>
          <span className="ld-ep">
            <Skel w={64} h={64} r={16} />
            <span className="ld-ep-body">
              <Skel w="70%" h={15} />
              <Skel w="44%" h={11} />
              <Skel w={86} h={22} r={999} />
            </span>
          </span>
        </li>
      ))}
    </ul>
  );
}

type Shape = "page" | "cards" | "list" | "episode";

function Shapes({ shape }: { shape: Shape }) {
  if (shape === "episode")
    return (
      <div className="ld-shapes ld-shapes-episode">
        <Skel h={74} r={18} />
        <Skel h={120} r={18} />
        <Skel h={56} r={24} w="70%" style={{ alignSelf: "center" }} />
      </div>
    );
  if (shape === "cards")
    return (
      <div className="ld-shapes ld-shapes-cards">
        <Skel h={180} r={18} />
        <Skel h={180} r={18} />
        <Skel h={180} r={18} />
      </div>
    );
  if (shape === "list")
    return (
      <div className="ld-shapes">
        {[0, 1, 2, 3].map((i) => (
          <Skel key={i} h={52} r={14} />
        ))}
      </div>
    );
  return (
    <div className="ld-shapes">
      <Skel h={18} w="34%" />
      <Skel h={96} r={18} />
      <Skel h={12} w="62%" />
      <Skel h={12} w="48%" />
    </div>
  );
}

/** What a page or tab shows until its data is there. Also moves the top line. */
export function PageLoading({ label, shape = "page", className = "" }: { label?: string; shape?: Shape; className?: string }) {
  useTopLine(true);
  return (
    <div className={`ld-page ${className}`} role="status" aria-live="polite" data-testid="page-loading">
      <div className="ld-page-head">
        <Wave size="lg" />
        <span>{label ?? t("正在打开…")}</span>
      </div>
      <Shapes shape={shape} />
    </div>
  );
}

const sinceMs = (started?: number | string | null) =>
  started == null ? null : typeof started === "number" ? (started < 1e12 ? started * 1000 : started) : Date.parse(started);

/** Seconds since `started` (epoch seconds, ms or ISO), ticking once a second; from mount if unknown. */
export function useElapsed(started?: number | string | null, on = true): number {
  const mounted = useRef(Date.now());
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!on) return;
    mounted.current = mounted.current || Date.now();
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [on]);
  const from = sinceMs(started) ?? mounted.current;
  return Math.max(0, Math.round((now - from) / 1000));
}

export function fmtSpan(s: number): string {
  s = Math.max(0, Math.round(s));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
}

/** "约 3 分钟" etc. for a number of seconds still to go. */
export function fmtLeft(s: number): string {
  if (s <= 10) return t("马上就好");
  if (s < 60) return t("不到 1 分钟");
  const m = Math.round(s / 60);
  return t("约 {n} 分钟", { n: m });
}

/**
 * Seconds left: from the progress so far when the job reports it (after a few seconds of data),
 * else from how long this kind of job usually takes. null = no honest estimate yet.
 */
export function estimateLeft(elapsed: number, progress?: number | null, typical?: number): number | null {
  if (progress != null && progress >= 0.03 && elapsed >= 5) return (elapsed * (1 - progress)) / progress;
  if (typical) return typical - elapsed;
  return null;
}

/** The server's stage line minus the step name it repeats ("识别 Pei 的分轨 · 第 41/70 分钟" → "第 41/70 分钟"). */
const detail = (stage: string | undefined, label: string) =>
  !stage || stage === label ? "" : stage.startsWith(label) ? stage.slice(label.length).replace(/^[\s·:：,，…-]+/, "") : stage;

export interface JobStep {
  label: string;
  state: "done" | "now" | "todo";
  /** fraction of the current step, shown as a percentage next to it */
  progress?: number;
}

/**
 * A long job: title, a bar (filling when the progress is known, sliding when not), the steps,
 * time used and roughly how long is left. `typical` = how long it usually takes, in seconds.
 */
export function JobProgress(props: {
  title: string;
  stage?: string;
  progress?: number | null;
  steps?: JobStep[];
  started?: number | string | null;
  typical?: number;
  actions?: ReactNode;
  testId?: string;
  /** test id of the current step's row */
  stepTestId?: string;
  /** inside another card: no card of its own */
  flat?: boolean;
  className?: string;
}) {
  const { title, stage, progress, steps, started, typical, actions, testId, stepTestId, flat, className = "" } = props;
  const elapsed = useElapsed(started);
  const left = estimateLeft(elapsed, progress, typical);
  const known = progress != null;
  const pct = known ? Math.round(Math.min(Math.max(progress!, 0), 1) * 100) : null;
  const n = steps?.length ?? 0;
  const at = steps ? steps.findIndex((s) => s.state === "now") : -1;
  return (
    <section className={`ld-job ${flat ? "ld-job-flat" : "card"} ${className}`} role="status" aria-live="polite" data-testid={testId}>
      <div className="ld-job-head">
        <Wave />
        <strong>{title}</strong>
        <span className="ld-job-meta">
          {at >= 0 ? t("第 {i} 步 / 共 {n} 步", { i: at + 1, n }) : pct != null ? `${pct}%` : null}
        </span>
      </div>
      <div
        className={`ld-bar ${known ? "" : "ld-bar-indeterminate"}`}
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct ?? undefined}
        aria-label={title}
      >
        <span style={known ? { width: `${Math.max(pct!, 2)}%` } : undefined} />
      </div>
      {steps ? (
        <ol className="ld-steps">
          {steps.map((s, i) => (
            <li key={i} className={`ld-step ld-step-${s.state}`} data-testid={s.state === "now" ? stepTestId : undefined}>
              <span className="ld-step-ic">{s.state === "done" ? "✓" : s.state === "now" ? <Wave /> : null}</span>
              <span>
                {s.label}
                {s.state === "now" && s.progress != null && ` · ${Math.round(s.progress * 100)}%`}
              </span>
              {s.state === "now" && detail(stage, s.label) && <span className="ld-step-detail">{detail(stage, s.label)}</span>}
            </li>
          ))}
        </ol>
      ) : (
        stage && <p className="ld-job-stage">{stage}</p>
      )}
      <div className="ld-job-foot">
        <span>
          {t("已用")} <b className="mono">{fmtSpan(elapsed)}</b>
        </span>
        {left != null && (
          <span data-testid={testId ? `${testId}-left` : undefined}>
            {left > 0 ? (
              <>
                {t("预计还要")} <b>{fmtLeft(left)}</b>
              </>
            ) : (
              t("比平时久一点，还在做")
            )}
          </span>
        )}
      </div>
      {actions && <div className="ld-job-actions">{actions}</div>}
    </section>
  );
}

/** A row for a wait of a few seconds (an AI reply, a lookup): the wave, what is happening, time used. */
export function Waiting({ label, hint, className = "" }: { label: string; hint?: string; className?: string }) {
  const s = useElapsed();
  return (
    <div className={`ld-waiting ${className}`} role="status" aria-live="polite" data-testid="waiting">
      <Wave />
      <span>
        {label}
        <span className="ld-waiting-sub">
          {hint ? `${hint} · ` : ""}
          {t("已用 {s} 秒", { s })}
        </span>
      </span>
    </div>
  );
}

/** Button content while its action runs: the wave + a short label, keeping the button's width steady. */
export function BusyLabel({ busy, label, busyLabel }: { busy: boolean; label: ReactNode; busyLabel?: ReactNode }) {
  if (!busy) return <>{label}</>;
  return (
    <span className="ld-btn-busy">
      <Wave />
      {busyLabel ?? label}
    </span>
  );
}

const topLine = { n: 0, listeners: new Set<() => void>() };

/** Keeps the top line moving while `on` (page loads use it; started requests move it by themselves). */
export function useTopLine(on: boolean) {
  useEffect(() => {
    if (!on) return;
    topLine.n++;
    topLine.listeners.forEach((l) => l());
    return () => {
      topLine.n--;
      topLine.listeners.forEach((l) => l());
    };
  }, [on]);
}

/** The thin moving line at the very top of the window. Rendered once, by this feature's nav entry. */
export function TopLine() {
  const [req, setReq] = useState(0);
  const [pages, setPages] = useState(topLine.n);
  useEffect(() => subscribe(setReq), []);
  useEffect(() => {
    const l = () => setPages(topLine.n);
    topLine.listeners.add(l);
    l();
    return () => {
      topLine.listeners.delete(l);
    };
  }, []);
  const on = req + pages > 0;
  return <span className={`ld-topline ${on ? "is-on" : ""}`} aria-hidden="true" data-testid="top-line" data-on={on ? "1" : "0"} />;
}
