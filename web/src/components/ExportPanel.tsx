import { useEffect, useRef, useState } from "react";
import type { ExportJob } from "../api";
import { api } from "../api";
import { t } from "../i18n";
import { BusyLabel, JobProgress } from "../features/loading/Loading";

const num = (v: number | null | undefined, unit: string) => (v == null ? "—" : `${v.toFixed(1)} ${unit}`);

/** Master the current version to MP3/WAV and show the result: the 导出 step page (`inline`), or a button + popover. */
export function ExportPanel({ id, version, inline = false }: { id: string; version: string; inline?: boolean }) {
  const [popOpen, setOpen] = useState(false);
  const open = inline || popOpen;
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
  // edits or music changed since this export
  const stale = job?.state === "done" && (job.version !== version || !!job.music_stale);
  return (
    <div className={inline ? "export export-inline" : "export"}>
      {!inline && (
      <button
        type="button"
        className="btn btn-primary"
        aria-expanded={open}
        onClick={() => {
          if (!open && !running) poll(); // the music may have changed on another page
          setOpen((o) => !o);
        }}
        data-testid="export-toggle"
      >
        <BusyLabel busy={running} label={t("导出")} busyLabel={t("导出中 {p0}%", { p0: Math.round((job?.progress ?? 0) * 100) })} />
      </button>
      )}
      {open && (
        <div className={inline ? "export-page card" : "export-pop"} role={inline ? undefined : "dialog"} aria-label={t("导出成品")}>
          <h2>{t("导出成品")}</h2>
          <p className="muted small">{t("母带处理：轻压缩 + 响度 −16 LUFS + 真峰值 ≤ −1 dBTP（播客平台标准）。导出的是当前版本，原始录音不变。")}</p>
          <div className="row gap8">
            <label>
              <input type="checkbox" checked={mp3} onChange={(e) => setMp3(e.target.checked)} disabled={running} /> {t("MP3（体积小，分享 / 备用）")}
            </label>
            <label>
              <input type="checkbox" checked={wav} onChange={(e) => setWav(e.target.checked)} disabled={running} /> {t("WAV（上传平台用，音质最好）")}
            </label>
          </div>
          <button type="button" className="btn btn-primary" onClick={start} disabled={running || (!mp3 && !wav)} data-testid="export-start">
            <BusyLabel busy={running} label={job ? t("重新导出") : t("开始导出")} busyLabel={t("导出中…")} />
          </button>
          {running && (
            <JobProgress
              flat
              title={t("正在导出成品")}
              stage={job?.stage}
              progress={job?.progress ?? 0}
              started={job?.started}
              testId="export-progress"
            />
          )}
          {err && <p className="error small">{err}</p>}
          {job?.state === "error" && <p className="error small">{t("导出失败：")}{job.error}</p>}
          {job?.state === "done" && job.result && (
            <div className="export-result" data-testid="export-result">
              {stale && <p className="small warn">{t("这是之前版本的导出，之后又有改动；要最新版请重新导出。")}</p>}
              <dl className="small">
                <dt>{t("响度")}</dt>
                <dd>{t("{out}（原始 {in}）", { out: num(rep?.output_lufs, "LUFS"), in: num(rep?.input_lufs, "LUFS") })}</dd>
                <dt>{t("真峰值")}</dt>
                <dd>
                  {t("{out}（原始 {in}）", { out: num(rep?.output_true_peak_db, "dBTP"), in: num(rep?.input_true_peak_db, "dBTP") })}
                  {job.result.mp3?.true_peak_db != null && <> · MP3 {num(job.result.mp3.true_peak_db, "dBTP")}</>}
                </dd>
                <dt>{t("压缩")}</dt>
                <dd>
                  {t("平均 {mean}，最多 {max} · 限幅只碰了 {pct}% 的时间", {
                    mean: num(rep?.comp_mean_gr_db, "dB"),
                    max: num(rep?.comp_max_gr_db, "dB"),
                    pct: (rep?.limiter_active_pct ?? 0).toFixed(2),
                  })}
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
                {t("打开导出文件夹")}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
