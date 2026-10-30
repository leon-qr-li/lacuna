import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { fmt } from "../../api";
import { t } from "../../i18n";
import { BusyLabel, Wave, fmtSpan, useElapsed } from "../loading/Loading";
import type { Credit } from "../library/api";
import { creditFixApi } from "./api";
import type { FixResult, FixView, Found } from "./api";
import "./credit-fix.css";

/** Other buttons on the page (the music page has two) reload when one of them changes something. */
const CHANGED = "lacuna:credit-fix";
const POLL_MS = 2500;

/** 「作者 · 出处」: the composer of a score (the performer of a song), then the film or album. */
export function authorLine(c: Partial<Credit> | Found): string {
  const who = c.film ? c.composer || c.artist : c.artist || c.composer;
  const from = c.film ? t("《{film}》原声", { film: c.film }) : c.album ? `《${c.album}》` : "";
  return [who, from].filter(Boolean).join(" · ");
}

interface Row {
  on: boolean;
  found: Found;
  edit: boolean;
}

const FIELDS: { key: keyof Found; label: string }[] = [
  { key: "title", label: t("曲名") },
  { key: "composer", label: t("作曲") },
  { key: "artist", label: t("演唱") },
  { key: "film", label: t("电影 / 剧") },
  { key: "album", label: t("原声专辑") },
  { key: "year", label: t("年份") },
];

const known = (f: Found) => !!(f.title || f.film);

/**
 * 一键修复曲名和作者 (decision 2026-10-30-credit-fix). With `episode`: the music page's button, for the music
 * only that episode has; without: the library page's, for the shared music. One sentence on where the music
 * comes from, LACUNA looks every track up, and the answers wait in a list to tick; nothing changes before
 * 采用. The lookup runs on the server, so the dialog can be closed meanwhile.
 */
export function CreditFix({
  episode,
  small = false,
  onApplied,
  testId = "credit-fix",
}: {
  episode?: string;
  small?: boolean;
  onApplied?: (n: number) => void;
  testId?: string;
}) {
  const [v, setV] = useState<FixView | null>(null);
  const [open, setOpen] = useState(false);
  const [retry, setRetry] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [redo, setRedo] = useState(false);
  const [rows, setRows] = useState<Record<string, Row>>({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const shownJob = useRef<string | null>(null);

  const load = useCallback(() => {
    creditFixApi.view(episode).then(setV, () => undefined);
  }, [episode]);
  useEffect(() => {
    load();
    window.addEventListener(CHANGED, load);
    return () => window.removeEventListener(CHANGED, load);
  }, [load]);

  const job = v?.job ?? null;
  const running = job?.state === "running";
  useEffect(() => {
    if (!running) return;
    const id = window.setInterval(load, POLL_MS);
    return () => window.clearInterval(id);
  }, [running, load]);
  // a finished lookup: its answers become the rows to tick (once per lookup, so edits survive polling)
  useEffect(() => {
    if (!job || job.state === "running" || shownJob.current === job.started_at) return;
    shownJob.current = job.started_at;
    setRows(Object.fromEntries(job.results.map((r) => [r.asset_id, { on: r.pick, found: { ...r.found }, edit: false }])));
    if (job.state === "done") window.dispatchEvent(new Event(CHANGED));
  }, [job]);
  useEffect(() => {
    if (!open) return;
    const key = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [open]);

  const elapsed = useElapsed(job?.started_at, running);
  if (!v || (v.own === 0 && !job)) return null;

  const act = async (p: Promise<FixView>, after?: (r: FixView) => void) => {
    setBusy(true);
    setErr(null);
    try {
      const r = await p;
      setV(r);
      after?.(r);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const start = () =>
    act(creditFixApi.start(episode, prompt, redo), () => {
      setRetry(false);
      window.dispatchEvent(new Event(CHANGED));
    });
  const ticked = job?.state === "done" ? job.results.filter((r) => rows[r.asset_id]?.on && known(rows[r.asset_id].found)) : [];
  const apply = () =>
    act(creditFixApi.apply(episode, ticked.map((r) => ({ asset_id: r.asset_id, credit: rows[r.asset_id].found }))), (r) => {
      setOpen(false);
      window.dispatchEvent(new Event(CHANGED));
      onApplied?.(r.applied ?? 0);
    });
  const drop = () =>
    act(creditFixApi.discard(episode), () => {
      setOpen(false);
      window.dispatchEvent(new Event(CHANGED));
    });
  const setRow = (id: string, patch: Partial<Row>) => setRows((rs) => ({ ...rs, [id]: { ...rs[id], ...patch } }));
  const setField = (id: string, key: keyof Found, value: string) =>
    setRows((rs) => {
      const found = { ...rs[id].found, [key]: key === "year" ? (/^\d{4}$/.test(value.trim()) ? Number(value) : null) : value || null };
      return { ...rs, [id]: { ...rs[id], found, on: known(found) && rs[id].on } };
    });

  const confirmed = v.files.filter((f) => f.status === "confirmed").length;
  const todo = v.files.filter((f) => redo || f.status !== "confirmed");
  const ready = job?.state === "done" && job.results.length > 0;
  const label = running ? t("LACUNA 正在查曲名…") : ready ? t("曲名查好了，去看看") : t("一键修复曲名");
  const hot = ready || (!running && v.unknown > 0);
  const form = !job || retry;

  return (
    <>
      <button
        type="button"
        className={`btn ${small ? "btn-small " : ""}cfx-btn${hot ? " is-hot" : ""}`}
        disabled={!v.available && !job}
        title={!v.available ? t("没有 AI 密钥，暂时查不了") : v.unknown ? t("还有 {n} 首不知道曲名或没确认", { n: v.unknown }) : undefined}
        onClick={() => {
          setErr(null);
          setOpen(true);
        }}
        data-testid={testId}
      >
        {running ? <BusyLabel busy label={label} /> : <><span aria-hidden="true">✦</span> {label}</>}
      </button>
      {open &&
        createPortal(
          <div className="dlg-backdrop" onMouseDown={(e) => e.target === e.currentTarget && setOpen(false)}>
            <div className="dlg cfx-dlg" role="dialog" aria-modal="true" aria-labelledby="cfx-title" data-testid="credit-fix-dialog">
              <div className="cfx-head">
                <h2 id="cfx-title">
                  {job?.state === "done" && !retry
                    ? t("LACUNA 查好了 {n} 首，勾上的会改", { n: job.results.length })
                    : t("一键修复曲名和作者")}
                </h2>
                <button type="button" className="cfx-x" aria-label={t("关掉")} onClick={() => setOpen(false)}>
                  ✕
                </button>
              </div>

              {form && (
                <>
                  <p className="small muted">{t("LACUNA 听不到音乐，只能按你的描述、文件名、文件里的标签和时长去查。说得越具体越准。")}</p>
                  <label className="cfx-field">
                    <span className="cfx-label">{t("这些音乐是哪来的？（可以空着）")}</span>
                    <textarea
                      value={prompt}
                      maxLength={500}
                      rows={3}
                      onChange={(e) => setPrompt(e.target.value)}
                      placeholder={t("比如：全是《午夜凶铃》1998 年原声；片尾那首是电影的主题曲")}
                      data-testid="credit-fix-prompt"
                      autoFocus
                    />
                  </label>
                  <div className="cfx-field">
                    <span className="cfx-label">
                      {episode ? t("这次修这一集的 {n} 首歌", { n: todo.length }) : t("这次修共用的 {n} 首歌", { n: todo.length })}
                    </span>
                    {todo.length > 0 ? (
                      <ul className="cfx-files">
                        {todo.map((f) => (
                          <li key={f.id}>
                            <span className="cfx-fname">{f.name}</span>
                            <span className="muted mono">
                              {fmt(f.duration_s)} · {f.kind_label}
                            </span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="small muted">{t("这里的歌都已经确认过了。")}</p>
                    )}
                    {confirmed > 0 && (
                      <label className="row gap8 small cfx-redo">
                        <input type="checkbox" checked={redo} onChange={(e) => setRedo(e.target.checked)} data-testid="credit-fix-redo" />
                        {t("已确认的 {n} 首也重新查", { n: confirmed })}
                      </label>
                    )}
                    <span className="small muted">
                      {episode ? t("共用的片头片尾不在这里，要改去素材库。") : t("只属于某一集的歌，在那一集的「配乐」页修。")}
                    </span>
                  </div>
                </>
              )}

              {!form && running && (
                <div className="cfx-wait" role="status" data-testid="credit-fix-running">
                  <Wave />
                  <div>
                    <p>{t("LACUNA 正在上网查 {n} 首歌的曲名和作者… 已用 {t}", { n: job.files.length, t: fmtSpan(elapsed) })}</p>
                    <p className="small muted">{t("通常 1–3 分钟。可以先关掉这个窗口去做别的，查好了会留在这里。")}</p>
                  </div>
                </div>
              )}

              {!form && job?.state === "failed" && <p className="error small" data-testid="credit-fix-failed">{job.message}</p>}

              {!form && job?.state === "done" && (
                <>
                  {job.prompt && <p className="small muted">{t("你的描述：{p}", { p: job.prompt })}</p>}
                  {job.message && job.results.length === 0 && <p className="small">{job.message}</p>}
                  <ul className="cfx-rows" data-testid="credit-fix-results">
                    {job.results.map((r) => (
                      <ResultRow
                        key={r.asset_id}
                        r={r}
                        row={rows[r.asset_id] ?? { on: false, found: r.found, edit: false }}
                        onRow={(p) => setRow(r.asset_id, p)}
                        onField={(k, val) => setField(r.asset_id, k, val)}
                      />
                    ))}
                  </ul>
                  {job.sources.length > 0 && (
                    <details className="small muted cfx-sources">
                      <summary>{t("LACUNA 查了这些网页")}</summary>
                      <ul>
                        {job.sources.map((s) => (
                          <li key={s}>
                            <a href={s} target="_blank" rel="noreferrer">
                              {s}
                            </a>
                          </li>
                        ))}
                      </ul>
                    </details>
                  )}
                </>
              )}

              {err && <p className="error small">{err}</p>}

              <div className="dlg-actions cfx-actions">
                {form && (
                  <>
                    <span className="small muted grow">{t("查完先给你看，不会直接改")}</span>
                    <button type="button" className="btn btn-outline" onClick={() => (retry ? setRetry(false) : setOpen(false))}>
                      {t("取消")}
                    </button>
                    <button type="button" className="btn btn-primary" disabled={busy || todo.length === 0 || !v.available} onClick={() => void start()} data-testid="credit-fix-start">
                      <BusyLabel busy={busy} label={t("交给 LACUNA")} />
                    </button>
                  </>
                )}
                {!form && running && (
                  <button type="button" className="btn btn-outline" onClick={() => setOpen(false)}>
                    {t("先关掉")}
                  </button>
                )}
                {!form && job?.state === "failed" && (
                  <>
                    <button type="button" className="btn btn-outline" disabled={busy} onClick={() => void drop()}>
                      {t("关掉")}
                    </button>
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={() => {
                        setPrompt(job.prompt);
                        setRetry(true);
                      }}
                    >
                      {t("再试一次")}
                    </button>
                  </>
                )}
                {!form && job?.state === "done" && (
                  <>
                    <span className="small muted grow">{t("已经生成的 show notes 不会自动改，采用后请重新生成。")}</span>
                    <button type="button" className="btn btn-outline" disabled={busy} onClick={() => void drop()} data-testid="credit-fix-discard">
                      {t("都不要")}
                    </button>
                    <button
                      type="button"
                      className="btn btn-outline"
                      disabled={busy}
                      onClick={() => {
                        setPrompt(job.prompt);
                        setRetry(true);
                      }}
                    >
                      {t("换个说法再查")}
                    </button>
                    <button type="button" className="btn btn-primary" disabled={busy || ticked.length === 0} onClick={() => void apply()} data-testid="credit-fix-apply">
                      <BusyLabel busy={busy} label={t("采用勾上的 {n} 首", { n: ticked.length })} />
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}

function ResultRow({ r, row, onRow, onField }: { r: FixResult; row: Row; onRow: (p: Partial<Row>) => void; onField: (k: keyof Found, v: string) => void }) {
  const f = row.found;
  const ok = known(f);
  const sure = r.confidence >= 0.7;
  return (
    <li className={`cfx-row${row.on ? " is-on" : ""}`} data-testid="credit-fix-row">
      <input
        type="checkbox"
        checked={row.on && ok}
        disabled={!ok}
        onChange={(e) => onRow({ on: e.target.checked })}
        aria-label={t("采用「{name}」的结果", { name: r.name })}
      />
      <div className="cfx-row-main">
        <div className="cfx-old" title={r.old_line}>
          {r.name}
        </div>
        {ok ? (
          <div className="cfx-new">
            <strong>{f.title ? `“${f.title}”` : t("（曲名不详）")}</strong>
            <span>{[authorLine(f), f.year].filter(Boolean).join(" · ") || t("还不知道作者")}</span>
          </div>
        ) : (
          <div className="cfx-new is-none">{t("没查到，原来的名字不动")}</div>
        )}
        {r.note && <div className="small muted">{r.note}</div>}
        {r.alternatives.length > 0 && (
          <div className="row gap6 wrap">
            {r.alternatives.map((alt) => (
              <button
                key={alt}
                type="button"
                className="btn btn-small btn-outline"
                onClick={() => {
                  const [title, who] = alt.split(/\s+—\s+/);
                  onField("title", title.trim());
                  if (who) onField("composer", who.trim());
                  onRow({ on: true });
                }}
              >
                {t("换成：{alt}", { alt })}
              </button>
            ))}
          </div>
        )}
        {row.edit && (
          <div className="cfx-edit">
            {FIELDS.map((fd) => (
              <label key={fd.key}>
                <span className="small muted">{fd.label}</span>
                <input value={f[fd.key] ?? ""} onChange={(e) => onField(fd.key, e.target.value)} inputMode={fd.key === "year" ? "numeric" : undefined} />
              </label>
            ))}
          </div>
        )}
      </div>
      <div className="cfx-side">
        <span className={`cfx-conf ${!ok ? "is-none" : sure ? "is-hi" : "is-lo"}`}>
          {!ok ? t("没查到") : sure ? t("把握高") : r.alternatives.length ? t("有几个候选") : t("没太大把握")}
        </span>
        <button type="button" className="cfx-link small" onClick={() => onRow({ edit: !row.edit })}>
          {row.edit ? t("收起") : t("自己改")}
        </button>
      </div>
    </li>
  );
}
