import { useCallback, useEffect, useRef, useState } from "react";
import type { FsListing, ImportJob } from "../api";
import { api, fmt } from "../api";
import { t } from "../i18n";
import { JobProgress } from "../features/loading/Loading";
import type { JobStep } from "../features/loading/Loading";

const RUNNING = new Set(["queued", "running"]);
const STATE_LABEL: Record<ImportJob["state"], string> = {
  queued: t("排队中"),
  running: t("导入中"),
  done: t("已完成"),
  error: t("出错了"),
  interrupted: t("中断了"),
  cancelled: t("已取消"),
};

// the importer's steps and their share of the progress (lacuna_app/importer.py STEPS)
const STEPS: [string, number, string][] = [
  ["models", 0.04, t("准备识别模型")],
  ["asr_L", 0.34, t("识别 Leon 的分轨")],
  ["asr_P", 0.34, t("识别 Pei 的分轨")],
  ["features", 0.04, t("分析停顿、语速和重叠")],
  ["first_cut", 0.2, t("AI 第一刀")],
  ["episode", 0.04, t("生成审阅")],
];

function jobSteps(j: ImportJob): JobStep[] {
  let before = 0;
  return STEPS.map(([key, w, label]) => {
    const from = before;
    before += w;
    if (j.steps?.[key]) return { label, state: "done" };
    if (j.step === key) return { label, state: "now", progress: Math.min(Math.max((j.progress - from) / w, 0), 1) };
    return { label, state: "todo" };
  });
}

/** When the work started, counting earlier runs of a resumed import (elapsed_s) as time already used. */
function startedAt(j: ImportJob): number | undefined {
  return j.run_started ? Date.parse(j.run_started) - (j.elapsed_s ?? 0) * 1000 : undefined;
}

/** Folder browser on the local machine (the server only lists folders and audio files). */
export function FileBrowser({
  start,
  onPick,
  onClose,
  label = t("选择分轨文件"),
}: {
  start?: string;
  onPick: (path: string, listing: FsListing) => void;
  onClose: () => void;
  label?: string;
}) {
  const [ls, setLs] = useState<FsListing | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const open = (path?: string) =>
    api
      .fs(path)
      .then((l) => {
        setLs(l);
        setErr(null);
      })
      .catch((e) => setErr((e as Error).message));
  useEffect(() => {
    void open(start);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <div className="fs" role="dialog" aria-label={label}>
      <div className="row gap8 fs-head">
        <span className="mono small fs-path" title={ls?.path}>
          {ls?.path ?? "…"}
        </span>
        <button type="button" className="btn btn-small" onClick={onClose}>
          {t("关闭")}
        </button>
      </div>
      {err && <p className="error small">{err}</p>}
      {ls && (
        <>
          <div className="row gap8 wrap fs-roots">
            {ls.roots.map((r) => (
              <button key={r} type="button" className="btn btn-small btn-outline" onClick={() => void open(r)}>
                {r}
              </button>
            ))}
          </div>
          <ul className="fs-list">
            {ls.parent && (
              <li>
                <button type="button" className="fs-item" onClick={() => void open(ls.parent!)}>
                  {t("⬆ 上一级")}
                </button>
              </li>
            )}
            {ls.dirs.map((d) => (
              <li key={d.path}>
                <button type="button" className="fs-item" onClick={() => void open(d.path)}>
                  📁 {d.name}
                </button>
              </li>
            ))}
            {ls.files.map((f) => (
              <li key={f.path}>
                <button type="button" className="fs-item fs-file" onClick={() => onPick(f.path, ls)}>
                  🎙 {f.name}
                  <span className="muted small">
                    {f.duration != null ? fmt(f.duration) : ""} · {(f.size / 1e6).toFixed(0)} MB
                  </span>
                </button>
              </li>
            ))}
            {!ls.dirs.length && !ls.files.length && <li className="muted small">{t("这里没有文件夹或音频文件")}</li>}
          </ul>
        </>
      )}
    </div>
  );
}

function guess(ls: FsListing, who: "Leon" | "Pei", except: string): string | null {
  const f = ls.files.find((x) => x.path !== except && x.name.toLowerCase().includes(who.toLowerCase()));
  return f ? f.path : null;
}

function NewImport({ nextId, onStarted, onCancel }: { nextId: string; onStarted: () => void; onCancel: () => void }) {
  const [id, setId] = useState(nextId);
  const [title, setTitle] = useState("");
  const [leon, setLeon] = useState("");
  const [pei, setPei] = useState("");
  const [picking, setPicking] = useState<"leon" | "pei" | null>(null);
  const [lastDir, setLastDir] = useState<string | undefined>(undefined);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const pick = (path: string, ls: FsListing) => {
    setLastDir(ls.path);
    if (picking === "leon") {
      setLeon(path);
      if (!pei) setPei(guess(ls, "Pei", path) ?? "");
    } else {
      setPei(path);
      if (!leon) setLeon(guess(ls, "Leon", path) ?? "");
    }
    setPicking(null);
  };
  const start = async () => {
    setBusy(true);
    setErr(null);
    try {
      await api.startImport({ id: id.trim(), title: title.trim(), leon, pei });
      onStarted();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const name = (p: string) => p.split(/[\\/]/).pop();
  return (
    <section className="card import-new" aria-label={t("导入新一集")}>
      <div className="card-head">
        <h2>{t("导入新一集")}</h2>
      </div>
      <div className="import-grid">
        <label>
          {t("剧集编号")}
          <input value={id} onChange={(e) => setId(e.target.value)} data-testid="import-id" />
        </label>
        <label>
          {t("标题（可不填）")}
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder={`${id} · …`} data-testid="import-title" />
        </label>
        {(["leon", "pei"] as const).map((k) => {
          const v = k === "leon" ? leon : pei;
          return (
            <div key={k} className="import-track">
              <span className={`dot ${k}`} aria-hidden />
              <strong>{k === "leon" ? t("Leon 的分轨") : t("Pei 的分轨")}</strong>
              <span className={`small ${v ? "" : "muted"}`} title={v} data-testid={`import-${k}`}>
                {v ? name(v) : t("还没选")}
              </span>
              <button type="button" className="btn btn-small btn-outline" onClick={() => setPicking(k)}>
                {t("选择文件…")}
              </button>
            </div>
          );
        })}
      </div>
      {picking && <FileBrowser start={lastDir} onPick={pick} onClose={() => setPicking(null)} />}
      <p className="muted small">
        {t("原始录音只读，不会被改动。逐字识别和分析都在这台电脑上做，只有文字和数字会发给 Claude 做第一刀。 长录音要跑一阵，可以关掉这页，进度不会丢。")}
      </p>
      {err && <p className="error small">{err}</p>}
      <div className="row gap8">
        <button type="button" className="btn btn-primary" disabled={!leon || !pei || !id.trim() || busy} onClick={() => void start()}>
          {t("开始导入")}
        </button>
        <button type="button" className="btn" onClick={onCancel}>
          {t("取消")}
        </button>
      </div>
    </section>
  );
}

function JobRow({ j, onChange }: { j: ImportJob; onChange: () => void }) {
  const [err, setErr] = useState<string | null>(null);
  const act = (p: Promise<unknown>) => p.then(onChange).catch((e) => setErr((e as Error).message));
  const running = RUNNING.has(j.state);
  return (
    <li className={`job job-${j.state}`} data-testid="import-job" data-state={j.state}>
      <div className="row gap8 wrap">
        <strong>{j.title}</strong>
        {!running && <span className={`chip ${j.state === "done" ? "chip-ok" : ""}`}>{STATE_LABEL[j.state]}</span>}
        <span className="muted small">
          {j.tracks.L.name} + {j.tracks.P.name}
          {j.tracks.L.duration ? ` · ${fmt(j.tracks.L.duration)}` : ""}
        </span>
      </div>
      {running && (
        <>
          <JobProgress
            flat
            title={j.state === "queued" ? t("排队中，马上开始") : t("正在导入")}
            stage={j.stage}
            progress={j.progress}
            steps={jobSteps(j)}
            started={startedAt(j)}
            stepTestId="import-stage"
          />
        </>
      )}
      {j.state === "done" && j.result && (
        <p className="small">
          {j.result.engine === "rules"
            ? t("AI 第一刀（没有 Claude，只收紧了停顿）：{edits} 处改动，{review} 处需要你过目。", { edits: j.result.edits, review: j.result.to_review })
            : t("AI 第一刀：{edits} 处改动，{review} 处需要你过目。", { edits: j.result.edits, review: j.result.to_review })}
        </p>
      )}
      {j.error && j.state !== "done" && <p className="error small">{j.error}</p>}
      {err && <p className="error small">{err}</p>}
      <div className="row gap8">
        {j.state === "done" && (
          <a className="btn btn-primary btn-small linkbtn" href={`#/ep/${encodeURIComponent(j.id)}/review`}>
            {t("开始审阅")}
          </a>
        )}
        {running && (
          <button type="button" className="btn btn-small" onClick={() => void act(api.cancelImport(j.id))}>
            {t("取消")}
          </button>
        )}
        {["error", "interrupted", "cancelled"].includes(j.state) && (
          <button type="button" className="btn btn-small btn-outline-accent" onClick={() => void act(api.resumeImport(j.id))}>
            {t("继续")}
          </button>
        )}
        {!running && (
          <button type="button" className="btn btn-small" onClick={() => void act(api.forgetImport(j.id))}>
            {t("从列表移除")}
          </button>
        )}
      </div>
    </li>
  );
}

/** Import form + task panel. Polls while a job runs; a job finishing here opens its review. */
export function ImportPanel({ onEpisodesChanged, onOpen }: { onEpisodesChanged: () => void; onOpen: (id: string) => void }) {
  const [jobs, setJobs] = useState<ImportJob[] | null>(null);
  const [nextId, setNextId] = useState("EP001");
  const [form, setForm] = useState(false);
  const prev = useRef<Map<string, string>>(new Map());

  const refresh = useCallback(async () => {
    try {
      const r = await api.imports();
      setJobs(r.jobs);
      setNextId(r.next_id);
      const seen = prev.current;
      for (const j of r.jobs) {
        if (j.state === "done" && seen.has(j.id) && RUNNING.has(seen.get(j.id)!)) {
          onEpisodesChanged();
          onOpen(j.id); // finished while Leon is looking: straight into review
        }
      }
      prev.current = new Map(r.jobs.map((j) => [j.id, j.state]));
    } catch {
      /* server restarting: try again on the next tick */
    }
  }, [onEpisodesChanged, onOpen]);

  const active = jobs?.some((j) => RUNNING.has(j.state)) ?? false;
  useEffect(() => {
    void refresh();
  }, [refresh]);
  useEffect(() => {
    if (!active) return;
    const t = window.setInterval(() => void refresh(), 1500);
    return () => window.clearInterval(t);
  }, [active, refresh]);

  return (
    <div className="imports">
      {!form && (
        <button type="button" className="btn btn-primary" onClick={() => setForm(true)} disabled={active}>
          {t("导入新一集")}
        </button>
      )}
      {form && (
        <NewImport
          nextId={nextId}
          onCancel={() => setForm(false)}
          onStarted={() => {
            setForm(false);
            void refresh();
          }}
        />
      )}
      {!!jobs?.length && (
        <section aria-label={t("导入任务")}>
          <h2 className="sub">{t("导入任务")}</h2>
          <ul className="jobs">
            {jobs.map((j) => (
              <JobRow key={j.id} j={j} onChange={() => void refresh()} />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
