import { useEffect, useRef, useState } from "react";
import { migrateApi, relPath, sendFile, waitBack, type MigrateResult, type MigrateState } from "./api";
import { confirmDialog } from "../dialog/Dialog";
import { JobProgress } from "../loading/Loading";
import { t } from "../../i18n";
import "./migrate.css";

const PARALLEL = 4;
const gb = (n: number) => (n / 1e9 >= 1 ? `${(n / 1e9).toFixed(1)} GB` : `${Math.max(1, Math.round(n / 1e6))} MB`);

type Phase = "pick" | "sending" | "finishing" | "restarting" | "done";

/** 设置 → 从电脑搬过来 (cloud, the owner): copy the desktop's LACUNA_Workspace folder onto the server. */
export function MigrateCard() {
  const [st, setSt] = useState<MigrateState | null>(null);
  const [files, setFiles] = useState<{ rel: string; file: File }[]>([]);
  const [phase, setPhase] = useState<Phase>("pick");
  const [sent, setSent] = useState(0);
  const [started, setStarted] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [result, setResult] = useState<MigrateResult | null>(null);
  const aborts = useRef<Set<() => void>>(new Set());
  const stopped = useRef(false);
  useEffect(() => {
    migrateApi.state().then(setSt, () => setSt(null));
  }, []);
  if (!st) return null;

  const total = files.reduce((a, f) => a + f.file.size, 0);
  const pick = (list: FileList | null) => {
    setErr(null);
    const out: { rel: string; file: File }[] = [];
    for (const file of Array.from(list ?? [])) {
      const rel = relPath(file);
      if (rel) out.push({ rel, file });
    }
    setFiles(out);
  };

  const start = async () => {
    setErr(null);
    stopped.current = false;
    setPhase("sending");
    setStarted(Date.now());
    try {
      const have = (await migrateApi.state())?.staged ?? {};
      const todo = files.filter((f) => have[f.rel] !== f.file.size);   // already there: a resumed move
      const base = total - todo.reduce((a, f) => a + f.file.size, 0);
      const now = new Map<string, number>();
      const report = () => setSent(base + [...now.values()].reduce((a, b) => a + b, 0));
      report();
      let next = 0;
      const worker = async () => {
        while (next < todo.length && !stopped.current) {
          const f = todo[next++];
          const s = sendFile(f.rel, f.file, (n) => {
            now.set(f.rel, n);
            report();
          });
          aborts.current.add(s.abort);
          try {
            await s.done;
          } finally {
            aborts.current.delete(s.abort);
          }
        }
      };
      await Promise.all(Array.from({ length: PARALLEL }, worker));
      if (stopped.current) throw new Error(t("已停下。再点一次「开始搬」会接着传。"));
      setPhase("finishing");
      const r = await migrateApi.finish(files.length, total);
      setPhase("restarting");
      await waitBack();
      setResult(r);
      setPhase("done");
    } catch (e) {
      stopAll();
      setErr(String((e as Error).message ?? e));
      setPhase("pick");
    }
  };
  const stopAll = () => {
    stopped.current = true;
    for (const a of aborts.current) a();
    aborts.current.clear();
  };
  const clear = async () => {
    if (!(await confirmDialog({ message: t("清掉这次已经传上来的文件？下次要从头传。"), danger: true, confirmLabel: t("清掉") }))) return;
    await migrateApi.cancel();
    setSt(await migrateApi.state());
  };
  const stagedCount = Object.keys(st.staged).length;

  return (
    <section className="card migrate-card" aria-label={t("从电脑搬过来")} data-testid="migrate-card">
      <h2>{t("从电脑搬过来")}</h2>
      {phase === "done" && result ? (
        <>
          <p data-testid="migrate-done">
            {t("搬好了：{episodes} 集，{files} 个文件，共 {size}。电脑上的文件没有动过。", {
              episodes: result.episodes,
              files: result.files,
              size: gb(result.bytes),
            })}
          </p>
          <button className="btn" onClick={() => window.location.reload()}>
            {t("刷新页面")}
          </button>
        </>
      ) : phase !== "pick" ? (
        <JobProgress
          flat
          title={phase === "sending" ? t("正在上传") : phase === "finishing" ? t("正在放进工作区") : t("正在重新启动")}
          stage={phase === "sending" ? `${gb(sent)} / ${gb(total)}` : undefined}
          progress={phase === "sending" ? (total ? sent / total : 0) : null}
          started={started}
          testId="migrate-progress"
          actions={
            phase === "sending" && (
              <button className="btn btn-outline" onClick={stopAll}>
                {t("停下")}
              </button>
            )
          }
        />
      ) : (
        <>
          <p className="muted small">{t("把电脑上的整个工作区（剧集、素材库、学到的规则）复制到这里。电脑上的文件只读不改。")}</p>
          <ol className="small migrate-steps">
            <li>{t("先关掉电脑上的 LACUNA App。")}</li>
            <li>{t("点「选文件夹」，选 C:\\Projects\\LACUNA_Workspace。浏览器问要不要上传时，点「上传」。")}</li>
            <li>{t("点「开始搬」。传的时候别关这个页面；断了就再点一次，已经传好的不会重传。")}</li>
          </ol>
          {st.episodes > 0 && (
            <p className="small migrate-warn">{t("这里已经有 {n} 集。电脑上同名的文件会盖掉这里的。", { n: st.episodes })}</p>
          )}
          <div className="row gap8 migrate-row">
            <label className="btn btn-outline">
              {t("选文件夹")}
              <input
                type="file"
                className="migrate-input"
                data-testid="migrate-input"
                // @ts-expect-error: folder picking is not in React's input props
                webkitdirectory=""
                multiple
                onChange={(e) => pick(e.target.files)}
              />
            </label>
            <button className="btn" disabled={!files.length} onClick={start} data-testid="migrate-start">
              {t("开始搬")}
            </button>
            {stagedCount > 0 && (
              <button className="btn btn-ghost" onClick={clear}>
                {t("清掉已传的")}
              </button>
            )}
          </div>
          {files.length > 0 && (
            <p className="small" data-testid="migrate-picked">
              {t("选好了：{n} 个文件，共 {size}。", { n: files.length, size: gb(total) })}
            </p>
          )}
          {stagedCount > 0 && !files.length && (
            <p className="muted small">{t("上次已经传了 {n} 个文件，选同一个文件夹再点「开始搬」就接着传。", { n: stagedCount })}</p>
          )}
        </>
      )}
      {err && <p className="error small" role="alert">{err}</p>}
    </section>
  );
}
