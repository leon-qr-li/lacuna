import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { ExportJob } from "../api";
import { markStep } from "../features/onboarding/api";
import { api } from "../api";
import { t } from "../i18n";
import { BusyLabel, JobProgress } from "../features/loading/Loading";
import { useCloud } from "../features/auth/cloud";
import { askAfterExport } from "../features/feedback/Prompts";
import { TellUs } from "../features/feedback/parts";

const num = (v: number | null | undefined, unit: string) => (v == null ? "—" : `${v.toFixed(1)} ${unit}`);

/** The 导出 step: formats, start, download on the left; this episode and the platform standard on the right. */
export function ExportPanel({ id, version, pending = 0, summary }: { id: string; version: string; pending?: number; summary?: ReactNode }) {
  const cloud = useCloud();
  const [job, setJob] = useState<ExportJob | null>(null);
  const [mp3, setMp3] = useState(true);
  const [wav, setWav] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const timer = useRef<number | null>(null);
  const watched = useRef(false);

  const poll = () => {
    api
      .exportStatus(id)
      .then((r) => {
        setJob(r.job);
        if (r.job?.state === "running") timer.current = window.setTimeout(poll, 600);
        // an export this screen watched just finished: maybe one question (features/feedback)
        else if (watched.current && r.job?.state === "done") void askAfterExport();
        watched.current = r.job?.state === "running";
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
  const done = job?.state === "done" && !!job.result;
  const okLufs = rep?.output_lufs != null && Math.abs(rep.output_lufs + 16) <= 1;
  const okPeak = rep?.output_true_peak_db != null && rep.output_true_peak_db <= -0.95;
  const bar = (v: number | null | undefined, lo: number, hi: number) => `${v == null ? 0 : Math.min(Math.max((v - lo) / (hi - lo), 0.04), 1) * 100}%`;
  const fmtCard = (on: boolean, set: (v: boolean) => void, name: string, note: string, short: string) => (
    <label className={`xfmt${on ? " is-on" : ""}`}>
      <input type="checkbox" checked={on} onChange={(e) => set(e.target.checked)} disabled={running} aria-label={note} />
      <span className="xfmt-top">
        <b>{name}</b>
        <span className="chip">{on ? t("✓ 选中") : t("不导出")}</span>
      </span>
      <span className="small muted">{short}</span>
    </label>
  );
  return (
    <div className="export export-inline" role="region" aria-label={t("导出成品")}>
      <section className="card xmain">
        <div className="xhead">
          <div>
            <h2>{t("导出成品")}</h2>
            <p className="muted small">{t("母带处理：轻压缩 + 响度 −16 LUFS + 真峰值 ≤ −1 dBTP（播客平台标准）。导出的是当前版本，原始录音不变。")}</p>
          </div>
        </div>
        <div className="xfmts" data-tour="export-formats">
          {fmtCard(mp3, setMp3, "MP3", t("MP3（体积小，分享 / 备用）"), t("体积小，分享 / 备用"))}
          {fmtCard(wav, setWav, "WAV", t("WAV（上传平台用，音质最好）"), t("上传平台用，音质最好"))}
        </div>
        {/* G5: a quiet line, never a block */}
        {pending > 0 && (
          <p className="small warn-note" data-testid="export-pending">
            {t("还有 {n} 处改动没过目，导出会按现在的样子。", { n: pending })}{" "}
            <a href={`#/ep/${encodeURIComponent(id)}/review`}>{t("去审阅")}</a>
          </p>
        )}
        <button type="button" className="btn btn-primary xstart" onClick={start} disabled={running || (!mp3 && !wav)} data-testid="export-start" data-tour="export-start">
          <BusyLabel
            busy={running}
            label={job ? t("重新导出") : t("开始导出")}
            busyLabel={t("导出中 {p0}%", { p0: Math.round((job?.progress ?? 0) * 100) })}
          />
        </button>
        {running && (
          <JobProgress flat title={t("正在导出成品")} stage={job?.stage} progress={job?.progress ?? 0} started={job?.started} testId="export-progress" />
        )}
        {err && (
          <p className="error small">
            {err}
            <TellUs title={t("导出没有完成")} message={err} />
          </p>
        )}
        {job?.state === "error" && (
          <p className="error small">
            {t("导出失败：")}{job.error}
            <TellUs title={t("导出没有完成")} message={job.error} />
          </p>
        )}
        <div className="xdl" data-tour="export-download">
          <b className="small">{t("下载")}</b>
          {done ? (
            <div className="export-result" data-testid="export-result">
              {stale && <p className="small warn">{t("这是之前版本的导出，之后又有改动；要最新版请重新导出。")}</p>}
              <ul className="export-files row gap8 wrap">
                {Object.entries(job!.result!.files).sort(([a], [b]) => (a === "mp3" ? -1 : b === "mp3" ? 1 : 0)).map(([fmt, name]) => (
                  <li key={fmt}>
                    <a
                      className={`btn ${fmt === "mp3" ? "btn-primary" : "btn-outline"}`}
                      href={`/api/episodes/${encodeURIComponent(id)}/exports/${encodeURIComponent(name)}`}
                      download
                      title={name}
                      data-testid={`export-download-${fmt}`}
                      onClick={() => markStep("export")}
                    >
                      {t("下载 {format}", { format: fmt.toUpperCase() })}
                    </a>
                  </li>
                ))}
              </ul>
              {Object.entries(job!.result!.errors).map(([fmt, msg]) => (
                <p key={fmt} className="error small">
                  {fmt.toUpperCase()}：{msg}
                </p>
              ))}
              {cloud === false && (
                <button type="button" className="btn btn-outline btn-small xopen" onClick={() => api.openExports(id).catch(() => {})}>
                  {t("打开导出文件夹")}
                </button>
              )}
              <p className="small muted" data-tour="export-publish">
                {t("下一步可以在「发布」里生成节目简介和封面，再发到各个平台。")}{" "}
                <a href={`#/ep/${encodeURIComponent(id)}/publish`}>{t("去发布")}</a>
              </p>
            </div>
          ) : (
            <span className="small muted">{t("导出好以后，这里出现下载按钮。")}</span>
          )}
        </div>
      </section>
      <aside className="xside">
        {summary}
        <div className="card xstd" data-testid="export-standard" data-tour="export-standard">
          <div className="xstd-head">
            <b>{t("符合播客平台标准")}</b>
            {done && okLufs && okPeak && <span className="ok">✓</span>}
          </div>
          {done ? (
            <>
              <div className="xmeter">
                <span className="small muted xmeter-label">
                  {t("响度")} <b className={okLufs ? "ok" : "warn"}>{num(rep?.output_lufs, "LUFS")}</b>
                  <span>{t("（原始 {in}）", { in: num(rep?.input_lufs, "LUFS") })}</span>
                </span>
                <span className="xbar"><i className={okLufs ? "ok" : "warn"} style={{ width: bar(rep?.output_lufs, -30, -10) }} /></span>
              </div>
              <div className="xmeter">
                <span className="small muted xmeter-label">
                  {t("真峰值")} <b className={okPeak ? "ok" : "warn"}>{num(rep?.output_true_peak_db, "dBTP")}</b>
                  <span>{t("（上限 −1）")}</span>
                  {job!.result!.mp3?.true_peak_db != null && <span> · MP3 {num(job!.result!.mp3.true_peak_db, "dBTP")}</span>}
                </span>
                <span className="xbar"><i className={okPeak ? "ok" : "warn"} style={{ width: bar(rep?.output_true_peak_db, -12, 0) }} /></span>
              </div>
              <span className="small muted">
                {t("压缩")}：
                {t("平均 {mean}，最多 {max} · 限幅只碰了 {pct}% 的时间", {
                  mean: num(rep?.comp_mean_gr_db, "dB"),
                  max: num(rep?.comp_max_gr_db, "dB"),
                  pct: (rep?.limiter_active_pct ?? 0).toFixed(2),
                })}
              </span>
              <details className="small">
                <summary>{t("技术细节")}</summary>
                <dl className="small">
                  <dt>{t("响度")}</dt>
                  <dd>{t("{out}（原始 {in}）", { out: num(rep?.output_lufs, "LUFS"), in: num(rep?.input_lufs, "LUFS") })}</dd>
                  <dt>{t("真峰值")}</dt>
                  <dd>{t("{out}（原始 {in}）", { out: num(rep?.output_true_peak_db, "dBTP"), in: num(rep?.input_true_peak_db, "dBTP") })}</dd>
                </dl>
              </details>
            </>
          ) : (
            <span className="small muted">{t("导出后在这里显示响度、真峰值和压缩量。")}</span>
          )}
          <span className="small muted">{t("已按播客平台的响度标准处理，可以直接上传到 Apple Podcasts、Spotify、小宇宙等任何播客平台。")}</span>
        </div>
      </aside>
    </div>
  );
}
