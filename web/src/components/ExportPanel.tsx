import { useEffect, useRef, useState } from "react";
import type { ExportJob } from "../api";
import { api } from "../api";

const num = (v: number | null | undefined, unit: string) => (v == null ? "—" : `${v.toFixed(1)} ${unit}`);

/** Top-bar "导出" button + popover: master the current version to MP3/WAV and show the result. */
export function ExportPanel({ id, version }: { id: string; version: string }) {
  const [open, setOpen] = useState(false);
  const [job, setJob] = useState<ExportJob | null>(null);
  const [mp3, setMp3] = useState(true);
  const [wav, setWav] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  const poll = () => {
    api
      .exportStatus(id)
      .then((r) => {
        setJob(r.job);
        if (r.job?.state === "running") timer.current = window.setTimeout(poll, 600);
      })
      .catch((e) => setErr(String(e.message ?? e)));
  };
  useEffect(() => {
    poll();
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const start = async () => {
    setErr(null);
    const formats = [...(mp3 ? ["mp3"] : []), ...(wav ? ["wav"] : [])];
    try {
      const r = await api.startExport(id, formats);
      setJob(r.job);
      timer.current = window.setTimeout(poll, 400);
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  const running = job?.state === "running";
  const rep = job?.result?.report;
  const stale = job?.state === "done" && job.version !== version;
  return (
    <div className="export">
      <button
        type="button"
        className="btn btn-primary"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        data-testid="export-toggle"
      >
        {running ? `导出中 ${Math.round((job?.progress ?? 0) * 100)}%` : "导出"}
      </button>
      {open && (
        <div className="export-pop" role="dialog" aria-label="导出成品">
          <h2>导出成品</h2>
          <p className="muted small">母带处理：轻压缩 + 响度 −16 LUFS + 真峰值 ≤ −1 dBTP（播客平台标准）。导出的是当前版本，原始录音不变。</p>
          <div className="row gap8">
            <label>
              <input type="checkbox" checked={mp3} onChange={(e) => setMp3(e.target.checked)} disabled={running} /> MP3（发布用）
            </label>
            <label>
              <input type="checkbox" checked={wav} onChange={(e) => setWav(e.target.checked)} disabled={running} /> WAV（存档用）
            </label>
          </div>
          <button type="button" className="btn btn-primary" onClick={start} disabled={running || (!mp3 && !wav)} data-testid="export-start">
            {running ? "导出中…" : job ? "重新导出" : "开始导出"}
          </button>
          {running && (
            <div className="export-progress" data-testid="export-progress">
              <progress max={1} value={job?.progress ?? 0} /> <span className="small">{job?.stage}</span>
            </div>
          )}
          {err && <p className="error small">{err}</p>}
          {job?.state === "error" && <p className="error small">导出失败：{job.error}</p>}
          {job?.state === "done" && job.result && (
            <div className="export-result" data-testid="export-result">
              {stale && <p className="small warn">这是之前版本的导出，之后又有改动；要最新版请重新导出。</p>}
              <dl className="small">
                <dt>响度</dt>
                <dd>{num(rep?.output_lufs, "LUFS")}（原始 {num(rep?.input_lufs, "LUFS")}）</dd>
                <dt>真峰值</dt>
                <dd>
                  {num(rep?.output_true_peak_db, "dBTP")}（原始 {num(rep?.input_true_peak_db, "dBTP")}）
                  {job.result.mp3?.true_peak_db != null && <> · MP3 {num(job.result.mp3.true_peak_db, "dBTP")}</>}
                </dd>
                <dt>压缩</dt>
                <dd>
                  平均 {num(rep?.comp_mean_gr_db, "dB")}，最多 {num(rep?.comp_max_gr_db, "dB")} · 限幅只碰了 {(rep?.limiter_active_pct ?? 0).toFixed(2)}% 的时间
                </dd>
              </dl>
              <ul className="export-files">
                {Object.entries(job.result.files).map(([fmt, name]) => (
                  <li key={fmt}>
                    <a href={`/api/episodes/${encodeURIComponent(id)}/exports/${encodeURIComponent(name)}`} download>
                      {name}
                    </a>
                  </li>
                ))}
              </ul>
              {Object.entries(job.result.errors).map(([fmt, msg]) => (
                <p key={fmt} className="error small">
                  {fmt.toUpperCase()}：{msg}
                </p>
              ))}
              <button type="button" className="btn btn-outline btn-small" onClick={() => api.openExports(id).catch(() => {})}>
                打开导出文件夹
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
