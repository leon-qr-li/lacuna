import { useCallback, useRef, useState } from "react";
import { t } from "../../i18n";
import type { OnProgress } from "./send";
import "./upload-progress.css";

export type UploadState = "wait" | "send" | "work" | "done" | "dup" | "error";
export type UploadRow = { name: string; size: number; f: number; state: UploadState; msg?: string; started?: number };

const mb = (b: number) => (b >= 1024 ** 3 ? `${(b / 1024 ** 3).toFixed(2)} GB` : `${(b / 1024 ** 2).toFixed(b < 10 * 1024 ** 2 ? 1 : 0)} MB`);

function left(r: UploadRow): string | null {
  if (r.state !== "send" || !r.started || r.f <= 0.02) return null;
  const s = ((Date.now() - r.started) / 1000) * ((1 - r.f) / r.f);
  if (s < 5) return null;
  return s < 60 ? t("还剩约 {n} 秒", { n: Math.ceil(s / 5) * 5 }) : t("还剩约 {n} 分钟", { n: Math.ceil(s / 60) });
}

/** The bar and its words for one file: waiting, how much has gone, the server reading it. */
export function UploadMeter({ r }: { r: UploadRow }) {
  const pct = Math.round(r.f * 100);
  const working = r.state === "work";
  const words =
    r.state === "wait"
      ? t("排队中")
      : working
        ? t("已传完，正在读取音频…")
        : `${pct}% · ${mb(r.f * r.size)} / ${mb(r.size)}`;
  const rest = left(r);
  return (
    <span className="upm" data-testid="upload-meter">
      <span
        className={`upm-bar ${working ? "is-work" : ""}`}
        role="progressbar"
        aria-label={t("上传进度：{name}", { name: r.name })}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={working ? 100 : pct}
      >
        <span style={{ width: `${working ? 100 : pct}%` }} />
      </span>
      <span className="upm-words mono">
        {words}
        {rest && ` · ${rest}`}
      </span>
    </span>
  );
}

/** Rows of files being uploaded (name + bar); finished files leave the list to the page's own message. */
export function UploadRows({ rows }: { rows: UploadRow[] }) {
  const busy = rows.filter((r) => r.state === "wait" || r.state === "send" || r.state === "work");
  if (!busy.length) return null;
  return (
    <ul className="upr" data-testid="upload-progress" aria-live="polite">
      {busy.map((r, i) => (
        <li key={`${i}-${r.name}`}>
          <span className="upr-name" title={r.name}>
            {r.name}
          </span>
          <UploadMeter r={r} />
        </li>
      ))}
    </ul>
  );
}

/** The rows' state; `track(i)` marks file i as started and is its progress callback (pass it to libraryApi.uploadAsset). */
export function useUploadRows() {
  const [rows, setRows] = useState<UploadRow[]>([]);
  const last = useRef<number[]>([]);
  const start = useCallback((files: File[]) => {
    last.current = files.map(() => 0);
    setRows(files.map((f) => ({ name: f.name, size: f.size, f: 0, state: "wait" })));
  }, []);
  const patch = useCallback((i: number, p: Partial<UploadRow>) => setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...p } : r))), []);
  /** Marks file i as being sent now (called right when its upload starts). */
  const track = useCallback(
    (i: number): OnProgress => {
      setRows((rs) => rs.map((r, j) => (j === i && r.state === "wait" ? { ...r, state: "send", started: Date.now() } : r)));
      return (f, phase) => {
        // at most one repaint per percent: a 1 GB file reports thousands of times
        const pct = Math.floor(f * 100);
        if (phase === "send" && pct === last.current[i] && f < 1) return;
        last.current[i] = pct;
        setRows((rs) =>
          rs.map((r, j) => (j === i ? { ...r, f, state: phase, started: r.started ?? Date.now() } : r)),
        );
      };
    },
    [],
  );
  return { rows, start, patch, track };
}
