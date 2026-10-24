// Building blocks of the admin pages: icons, cards, numbers, small charts, dialogs, the toast, and the data hook
// that reads either the real API or the demo data (demo mode: nothing is ever written).
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { get, type AdminError } from "./api";
import { demoData } from "./demo";
import { lang, locale, t } from "./i18n";

// ------------------------------------------------------------------ icons
const IC: Record<string, string> = {
  home: "M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z",
  inbox: "M3 13h5l1.5 3h5L16 13h5M5 5h14l2 8v6a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-6z",
  users: "M9 4.5a3.5 3.5 0 1 1 0 7 3.5 3.5 0 0 1 0-7M2.5 20c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5M16 4.5a3.5 3.5 0 0 1 0 7M18 14.8c2 .7 3.2 2.4 3.5 5.2",
  mail: "M5 5h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2M3 7l9 6 9-6",
  clock: "M12 3a9 9 0 1 1 0 18 9 9 0 0 1 0-18M12 7v5l3 2",
  mic: "M12 3a3 3 0 0 1 3 3v5a3 3 0 0 1-6 0V6a3 3 0 0 1 3-3M5 11a7 7 0 0 0 14 0M12 18v3",
  trash: "M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3",
  spark: "M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6",
  chart: "M4 20V10M10 20V4M16 20v-7M22 20H2",
  pulse: "M3 12h4l2-6 4 12 2-6h6",
  gear: "M12 9a3 3 0 1 1 0 6 3 3 0 0 1 0-6M19 12a7 7 0 0 0-.1-1.2l2-1.6-2-3.4-2.4 1a7 7 0 0 0-2-1.2L14 3h-4l-.5 2.6a7 7 0 0 0-2 1.2l-2.4-1-2 3.4 2 1.6a7 7 0 0 0 0 2.4l-2 1.6 2 3.4 2.4-1a7 7 0 0 0 2 1.2L10 21h4l.5-2.6a7 7 0 0 0 2-1.2l2.4 1 2-3.4-2-1.6c.1-.4.1-.8.1-1.2",
  log: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
  moon: "M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z",
  sun: "M12 8a4 4 0 1 1 0 8 4 4 0 0 1 0-8M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4",
  x: "M6 6l12 12M18 6 6 18",
  shield: "M12 3 4 6v6c0 4.5 3.4 8.3 8 9 4.6-.7 8-4.5 8-9V6z",
  star: "m12 3 2.8 5.7 6.2.9-4.5 4.4 1 6.2L12 17.3 6.5 20.2l1-6.2L3 9.6l6.2-.9z",
  plus: "M12 5v14M5 12h14",
  hand: "M7 11V6a2 2 0 1 1 4 0v5M11 10V4a2 2 0 1 1 4 0v6M15 9V6a2 2 0 1 1 4 0v8a7 7 0 0 1-7 7h-1a7 7 0 0 1-6-3.4L3 14a2 2 0 0 1 3.4-2L7 13",
  out: "M15 4h4a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-4M10 17l-5-5 5-5M5 12h11",
  menu: "M4 7h16M4 12h16M4 17h16",
  lock: "M6 11h12v9H6zM8 11V8a4 4 0 0 1 8 0v3",
  ext: "M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5",
};

export function Icon({ name, size = 16 }: { name: string; size?: number }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={IC[name] ?? ""} />
    </svg>
  );
}

// ------------------------------------------------------------------ formatting
export const fmtDate = (ts: number | null | undefined) => (ts ? new Date(ts * 1000).toLocaleDateString(locale) : "—");
export const fmtTime = (ts: number | null | undefined) =>
  ts ? new Date(ts * 1000).toLocaleString(locale, { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—";
export const fmtNum = (n: number | null | undefined, digits = 0) =>
  n === null || n === undefined || Number.isNaN(n) ? "—" : n.toLocaleString(locale, { maximumFractionDigits: digits, minimumFractionDigits: 0 });
export const fmtUsd = (n: number | null | undefined, digits = 2) => (n === null || n === undefined ? "—" : `$${n.toFixed(digits)}`);
export const fmtPct = (n: number | null | undefined, digits = 0) => (n === null || n === undefined ? "—" : `${(n * 100).toFixed(digits)}%`);
export function fmtBytes(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)} GB`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(0)} MB`;
  return `${Math.max(0, Math.round(n / 1e3))} KB`;
}
export function ago(ts: number | null | undefined, now = Date.now() / 1000): string {
  if (!ts) return "—";
  const s = Math.max(0, now - ts);
  if (s < 60) return t("刚刚");
  if (s < 3600) return t("{n} 分钟前", { n: Math.floor(s / 60) });
  if (s < 86400) return t("{n} 小时前", { n: Math.floor(s / 3600) });
  if (s < 86400 * 30) return t("{n} 天前", { n: Math.floor(s / 86400) });
  return fmtDate(ts);
}
export function duration(s: number | null | undefined): string {
  if (s === null || s === undefined) return "—";
  if (s < 3600) return t("{n} 分钟", { n: Math.max(1, Math.round(s / 60)) });
  if (s < 86400 * 2) return t("{n} 小时", { n: Math.round((s / 3600) * 10) / 10 });
  return t("{n} 天", { n: Math.round((s / 86400) * 10) / 10 });
}
export const initial = (s: string | null | undefined) => (s || "?").trim().slice(0, 1).toUpperCase();

// ------------------------------------------------------------------ demo mode
const DEMO = "lacuna.admin.demo";
let demo = (() => {
  try {
    return localStorage.getItem(DEMO) === "1";
  } catch {
    return false;
  }
})();
const demoSubs = new Set<(on: boolean) => void>();
export const isDemo = () => demo;
export function setDemo(on: boolean) {
  demo = on;
  try {
    localStorage.setItem(DEMO, on ? "1" : "0");
  } catch {
    /* private mode */
  }
  demoSubs.forEach((f) => f(on));
}
export function useDemo(): boolean {
  const [on, set] = useState(demo);
  useEffect(() => {
    demoSubs.add(set);
    return () => void demoSubs.delete(set);
  }, []);
  return on;
}

/** GET `url` (or its demo data); `reload` reads it again; `set` replaces it with an action's answer. */
export function useData<T>(url: string | null) {
  const on = useDemo();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [n, setN] = useState(0);
  useEffect(() => {
    if (!url) return;
    let live = true;
    setError(null);
    if (on) {
      setData(demoData(url) as T);
      return;
    }
    setData(null);
    get<T>(url).then(
      (d) => live && setData(d),
      (e) => live && setError((e as Error).message),
    );
    return () => {
      live = false;
    };
  }, [url, on, n]);
  const reload = useCallback(() => setN((x) => x + 1), []);
  return { data, error, reload, set: setData, demo: on };
}

/** Run a change: in demo mode only a toast says nothing is saved; otherwise its result, or a toast with the error. */
export async function act<T>(fn: () => Promise<T>, done?: string): Promise<T | null> {
  if (demo) {
    toast(t("演示数据，不会保存"));
    return null;
  }
  try {
    const out = await fn();
    if (done) toast(done);
    return out;
  } catch (e) {
    const err = e as AdminError;
    if (err.code !== "stepup") toast(err.message || t("出错了"), "bad");
    return null;
  }
}

// ------------------------------------------------------------------ toast
let toastHost: HTMLDivElement | null = null;
let toastTimer = 0;
export function toast(msg: string, tone: "ok" | "bad" = "ok") {
  if (!toastHost) {
    toastHost = document.createElement("div");
    toastHost.className = "a-toast-host";
    toastHost.setAttribute("role", "status");
    document.body.appendChild(toastHost);
  }
  toastHost.textContent = "";
  const el = document.createElement("div");
  el.className = `a-toast${tone === "bad" ? " bad" : ""}`;
  el.textContent = msg;
  el.dataset.testid = "toast";
  toastHost.appendChild(el);
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => el.remove(), 3200);
}

// ------------------------------------------------------------------ dialogs
type DialogSpec = { title: string; body?: ReactNode; ok: string; danger?: boolean; typed?: string; input?: { label: string; placeholder?: string; multiline?: boolean; value?: string } };

/** A dialog in a root of its own; resolves with the typed / entered text ("" when nothing to type), or null. */
export function dialog(spec: DialogSpec): Promise<string | null> {
  return new Promise((resolve) => {
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    const close = (v: string | null) => {
      root.unmount();
      host.remove();
      resolve(v);
    };
    root.render(<Dialog spec={spec} close={close} />);
  });
}

function Dialog({ spec, close }: { spec: DialogSpec; close: (v: string | null) => void }) {
  const [v, setV] = useState(spec.input?.value ?? "");
  const ok = spec.typed ? v.trim().toLowerCase() === spec.typed.toLowerCase() : spec.input ? v.trim().length > 0 : true;
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && close(null);
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [close]);
  return (
    <div className="a-scrim center" onMouseDown={(e) => e.target === e.currentTarget && close(null)}>
      <div className="a-modal" role="dialog" aria-modal="true" aria-label={spec.title} data-testid="dialog">
        <h3>{spec.title}</h3>
        {spec.body && <div className="a-modal-body">{spec.body}</div>}
        {spec.typed && (
          <label className="a-lbl">
            {t("输入「{w}」确认", { w: spec.typed })}
            <input className="a-inp" autoFocus value={v} onChange={(e) => setV(e.target.value)} data-testid="dialog-typed" />
          </label>
        )}
        {spec.input && (
          <label className="a-lbl">
            {spec.input.label}
            {spec.input.multiline ? (
              <textarea className="a-inp" autoFocus rows={4} value={v} placeholder={spec.input.placeholder} onChange={(e) => setV(e.target.value)} data-testid="dialog-input" />
            ) : (
              <input className="a-inp" autoFocus value={v} placeholder={spec.input.placeholder} onChange={(e) => setV(e.target.value)} data-testid="dialog-input" />
            )}
          </label>
        )}
        <div className="a-row end">
          <button type="button" className="a-btn" onClick={() => close(null)}>
            {t("取消")}
          </button>
          <button type="button" className={`a-btn ${spec.danger ? "danger-solid" : "pri"}`} disabled={!ok} onClick={() => close(v.trim())} data-testid="dialog-ok">
            {spec.ok}
          </button>
        </div>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ layout pieces
export function PageHead({ title, sub, actions }: { title: string; sub?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="a-ph">
      <div>
        <h1>{title}</h1>
        {sub && <p>{sub}</p>}
      </div>
      {actions && <div className="a-ph-act">{actions}</div>}
    </div>
  );
}

export function Card({ title, sub, right, children, pad = true, className = "", testid }: { title?: ReactNode; sub?: ReactNode; right?: ReactNode; children: ReactNode; pad?: boolean; className?: string; testid?: string }) {
  return (
    <section className={`a-card ${className}`} data-testid={testid}>
      {title && (
        <div className="a-card-h">
          <h2>{title}</h2>
          {sub && <span className="a-sub">{sub}</span>}
          {right && <div className="a-card-r">{right}</div>}
        </div>
      )}
      <div className={pad ? "a-card-b" : ""}>{children}</div>
    </section>
  );
}

export function Empty({ icon = "inbox", title, sub }: { icon?: string; title: string; sub?: string }) {
  return (
    <div className="a-empty">
      <Icon name={icon} size={28} />
      <b>{title}</b>
      {sub && <span>{sub}</span>}
    </div>
  );
}

export function Pill({ tone = "", children }: { tone?: "" | "ok" | "warn" | "bad" | "info" | "acc"; children: ReactNode }) {
  return <span className={`a-pill ${tone}`}>{children}</span>;
}

export function Tabs<K extends string>({ value, onChange, items }: { value: K; onChange: (k: K) => void; items: { id: K; label: string; n?: number | null }[] }) {
  return (
    <div className="a-tabs" role="tablist">
      {items.map((x) => (
        <button key={x.id} type="button" role="tab" aria-selected={value === x.id} onClick={() => onChange(x.id)} data-testid={`tab-${x.id}`}>
          {x.label}
          {x.n !== undefined && x.n !== null && <span className="n">{x.n}</span>}
        </button>
      ))}
    </div>
  );
}

export function Chips<K extends string>({ value, onChange, items }: { value: K; onChange: (k: K) => void; items: { id: K; label: string }[] }) {
  return (
    <>
      {items.map((x) => (
        <button key={x.id} type="button" className="a-chip" aria-pressed={value === x.id} onClick={() => onChange(x.id)}>
          {x.label}
        </button>
      ))}
    </>
  );
}

export function Switch({ on, onChange, label, disabled, testid }: { on: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean; testid?: string }) {
  return <button type="button" role="switch" aria-checked={on} aria-label={label} className="a-switch" disabled={disabled} onClick={() => onChange(!on)} data-testid={testid} />;
}

export function Avatar({ name, big }: { name: string | null | undefined; big?: boolean }) {
  return <span className={`a-av${big ? " big" : ""}`}>{initial(name)}</span>;
}

export function Who({ email, name, sub }: { email: string | null | undefined; name?: string | null; sub?: ReactNode }) {
  return (
    <span className="a-who">
      <Avatar name={name || email} />
      <span className="a-who-t">
        <b>{name || email || "—"}</b>
        {(sub ?? (name ? email : null)) && <span>{sub ?? email}</span>}
      </span>
    </span>
  );
}

export function Loading({ error }: { error?: string | null }) {
  return error ? <p className="a-error" role="alert">{error}</p> : <div className="a-loading" aria-busy="true">{t("加载中…")}</div>;
}

export function HBar({ label, value, max, text, tone }: { label: ReactNode; value: number; max: number; text: ReactNode; tone?: "warn" | "bad" }) {
  const pct = max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0;
  return (
    <div className="a-hb">
      <span>{label}</span>
      <div className={`a-bar ${tone ?? ""}`}>
        <i style={{ width: `${pct}%` }} />
      </div>
      <span className="n">{text}</span>
    </div>
  );
}

// ------------------------------------------------------------------ charts (plain SVG, no library)
export function Spark({ values, tone = "mu" }: { values: number[]; tone?: "up" | "dn" | "mu" }) {
  const v = values.length > 1 ? values : [0, ...(values.length ? values : [0])];
  const w = 120,
    h = 30;
  const max = Math.max(...v, 1),
    min = Math.min(...v, 0);
  const pts = v.map((x, i) => [(i / (v.length - 1)) * w, h - 3 - ((x - min) / (max - min || 1)) * (h - 6)]);
  const line = pts.map((p) => p.join(",")).join(" ");
  return (
    <svg className={`a-spark ${tone}`} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden="true">
      <polygon points={`0,${h} ${line} ${w},${h}`} className="fill" />
      <polyline points={line} className="ln" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

export function LineChart({ series, labels, height = 170, yfmt = (v: number) => String(Math.round(v)), names }: { series: number[][]; labels: string[]; height?: number; yfmt?: (v: number) => string; names?: string[] }) {
  const W = 560,
    l = 40,
    r = 10,
    tp = 10,
    b = 22,
    iw = W - l - r,
    ih = height - tp - b;
  const all = series.flat();
  const top = Math.max(...all, 1);
  const nice = top <= 4 ? 4 : Math.ceil(top / 4) * 4;
  const n = Math.max(2, labels.length);
  const step = iw / (n - 1);
  const y = (v: number) => tp + ih - (v / nice) * ih;
  return (
    <figure className="a-chart">
      <svg viewBox={`0 0 ${W} ${height}`} role="img" aria-label={names?.join(" / ")}>
        {[0, nice / 2, nice].map((v) => (
          <g key={v}>
            <line x1={l} x2={W - r} y1={y(v)} y2={y(v)} className="grid" />
            <text x={l - 6} y={y(v) + 4} textAnchor="end" className="tick">
              {yfmt(v)}
            </text>
          </g>
        ))}
        {labels.map((lb, i) =>
          labels.length <= 12 || i % Math.ceil(labels.length / 10) === 0 ? (
            <text key={i} x={l + i * step} y={height - 6} textAnchor="middle" className="tick">
              {lb}
            </text>
          ) : null,
        )}
        {series.map((sv, k) => {
          if (!sv.length) return null;
          const pts = sv.map((v, i) => [l + i * step, y(v)]);
          const line = pts.map((p) => p.join(",")).join(" ");
          const last = pts[pts.length - 1];
          return (
            <g key={k} className={`s${k}`}>
              {k === 0 && <polygon points={`${l},${tp + ih} ${line} ${last[0]},${tp + ih}`} className="area" />}
              <polyline points={line} className="ln" />
              <circle cx={last[0]} cy={last[1]} r={3.2} className="pt" />
            </g>
          );
        })}
      </svg>
      {names && (
        <figcaption className="a-legend">
          {names.map((nm, k) => (
            <span key={nm}>
              <i className={`s${k}`} />
              {nm}
            </span>
          ))}
        </figcaption>
      )}
    </figure>
  );
}

export function Bars({ values, labels, height = 150, fmt = (v: number) => String(v) }: { values: number[]; labels: string[]; height?: number; fmt?: (v: number) => string }) {
  const W = 560,
    l = 10,
    r = 10,
    tp = 16,
    b = 22,
    iw = W - l - r,
    ih = height - tp - b;
  const max = Math.max(...values, 1);
  const gap = iw / Math.max(1, values.length);
  const bw = gap * 0.62;
  return (
    <svg className="a-chart" viewBox={`0 0 ${W} ${height}`} role="img">
      <line x1={l} x2={W - r} y1={tp + ih} y2={tp + ih} className="grid" />
      {values.map((v, i) => {
        const bh = (v / max) * ih;
        const x = l + i * gap + (gap - bw) / 2;
        return (
          <g key={i}>
            <rect x={x} y={tp + ih - bh} width={bw} height={Math.max(bh, 1)} rx={3} className={i === values.length - 1 ? "bar last" : "bar"} />
            <text x={x + bw / 2} y={tp + ih - bh - 4} textAnchor="middle" className="val">
              {fmt(v)}
            </text>
            <text x={x + bw / 2} y={height - 6} textAnchor="middle" className="tick">
              {labels[i]}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export const weekLabels = (n: number) => Array.from({ length: n }, (_, i) => (i === n - 1 ? t("本周") : `-${n - 1 - i}`));

/** Closes on Escape and on a click outside: the user drawer. */
export function Drawer({ title, onClose, children, head }: { title: string; onClose: () => void; children: ReactNode; head?: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    ref.current?.focus();
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <div className="a-scrim" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <aside className="a-drawer" role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} ref={ref} data-testid="drawer">
        <div className="a-dh">
          {head}
          <button type="button" className="a-ib x" onClick={onClose} aria-label={t("关闭")}>
            <Icon name="x" />
          </button>
        </div>
        <div className="a-db">{children}</div>
      </aside>
    </div>
  );
}

export const isEn = lang === "en";
