import { useCallback, useEffect, useState } from "react";
import type { AppInfo } from "../api";
import { api } from "../api";

const KEY_SOURCE: Record<string, string> = {
  env: "环境变量",
  "registry-user": "Windows 用户环境变量",
  "registry-machine": "Windows 系统环境变量",
  keychain: "macOS 钥匙串",
  file: "本机文件",
};

/** Polls /api/app until the server answers with a different version (or again, after a plain restart). */
async function waitForRestart(from: string, sameVersionOk: boolean): Promise<void> {
  const end = Date.now() + 10 * 60_000; // first install of new packages can take a few minutes
  let wentDown = false;
  while (Date.now() < end) {
    await new Promise((r) => setTimeout(r, 1500));
    try {
      const info = await api.appInfo();
      if (info.version !== from || (sameVersionOk && wentDown)) return;
    } catch {
      wentDown = true;
    }
  }
}

/** Top-bar link to 设置, with a dot when an update is waiting. */
export function SettingsLink() {
  const [update, setUpdate] = useState(false);
  useEffect(() => {
    api
      .appInfo()
      .then((i) => setUpdate(i.update.available))
      .catch(() => setUpdate(false));
  }, []);
  return (
    <a className="btn btn-outline row" href="#/settings">
      设置{update ? " · 有新版本" : ""}
    </a>
  );
}

export function SettingsView() {
  const [info, setInfo] = useState<AppInfo | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [key, setKey] = useState("");

  const load = useCallback(() => api.appInfo().then(setInfo).catch((e) => setErr(String(e.message ?? e))), []);
  useEffect(() => {
    load();
  }, [load]);

  // while a download runs, follow its progress
  const job = info?.update.job;
  useEffect(() => {
    if (job?.state !== "running") return;
    const t = setInterval(load, 1000);
    return () => clearInterval(t);
  }, [job?.state, load]);

  const run = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(label);
    setErr(null);
    setMsg(null);
    try {
      await fn();
    } catch (e) {
      setErr(String((e as Error).message ?? e));
    } finally {
      setBusy(null);
    }
  };

  const check = () => run("check", async () => setInfo(await api.checkUpdate()));
  const prepare = () => run("prepare", async () => setInfo(await api.prepareUpdate()));
  const apply = () =>
    run("apply", async () => {
      const from = info!.version;
      await api.applyUpdate();
      setMsg("正在更新并重启，页面会自己刷新…");
      await waitForRestart(from, false);
      window.location.reload();
    });
  const saveKey = () =>
    run("key", async () => {
      const r = await api.saveApiKey(key.trim());
      setKey("");
      if (r.restarting) {
        setMsg("已保存，正在重启让它生效…");
        await waitForRestart(info!.version, true);
        window.location.reload();
      } else {
        setMsg("已保存。重启 LACUNA 后生效。");
        load();
      }
    });

  if (!info) return <p className={err ? "error pad" : "pad muted"}>{err ?? "读取中…"}</p>;
  const u = info.update;
  return (
    <main className="home settings">
      <h1>设置</h1>
      {msg && <p className="card" role="status">{msg}</p>}
      {err && <p className="error">{err}</p>}

      <section className="card" aria-label="版本">
        <div className="card-head">
          <h2>版本</h2>
          <span className="badge" data-testid="app-version">
            {info.installed ? info.version : "开发版"}
          </span>
        </div>
        {!info.installed && <p className="muted small">这是从源码直接运行的开发版，不在 App 里更新。</p>}
        {u.last_update && (
          <p className={u.last_update.ok ? "muted small" : "error"}>
            上次更新（{u.last_update.at}）：{u.last_update.message}
          </p>
        )}
        {info.installed && (
          <>
            {u.available ? (
              <div data-testid="update-available">
                <p>
                  有新版本 <strong>{u.latest}</strong>
                </p>
                {u.notes && <pre className="notes">{u.notes}</pre>}
                {job?.state === "running" ? (
                  <p className="muted">下载中 {Math.round((job.progress ?? 0) * 100)}%</p>
                ) : job?.state === "ready" ? (
                  <>
                    {info.busy.length > 0 && <p className="muted small">{info.busy.join("、")}还在进行，做完才能更新。</p>}
                    <button className="btn btn-primary" disabled={!!busy || info.busy.length > 0} onClick={apply}>
                      更新并重启
                    </button>
                    <p className="muted small">大约一两分钟。正在编辑的内容都已经自动保存。新版本起不来会自动回到现在的版本。</p>
                  </>
                ) : (
                  <>
                    {job?.state === "error" && <p className="error">{job.error}</p>}
                    <button className="btn btn-primary" disabled={!!busy} onClick={prepare}>
                      下载新版本
                    </button>
                  </>
                )}
              </div>
            ) : (
              <p className="muted">{u.error ?? (u.latest ? "已经是最新版本。" : "还没检查过更新。")}</p>
            )}
            <button className="btn btn-outline" disabled={!!busy} onClick={check}>
              {busy === "check" ? "检查中…" : "检查更新"}
            </button>
          </>
        )}
      </section>

      <section className="card" aria-label="Claude API key">
        <div className="card-head">
          <h2>Claude API key</h2>
          <span className={info.key.present ? "badge badge-confirmed" : "badge badge-unknown"} data-testid="key-state">
            {info.key.present ? `已设置（${KEY_SOURCE[info.key.source ?? ""] ?? info.key.source}）` : "没有设置"}
          </span>
        </div>
        <p className="muted small">
          AI 第一刀、聊天修改、发布资料要用它。只保存在这台电脑上{info.platform === "macOS" ? "（钥匙串）" : ""}，不会显示出来。
        </p>
        <div className="row gap">
          <input
            className="grow"
            type="password"
            autoComplete="off"
            placeholder="sk-ant-…"
            aria-label="API key"
            value={key}
            onChange={(e) => setKey(e.target.value)}
          />
          <button className="btn btn-outline" disabled={!!busy || key.trim().length < 20} onClick={saveKey}>
            {info.key.present ? "换一个" : "保存"}
          </button>
        </div>
      </section>

      <section className="card" aria-label="这台电脑">
        <h2>这台电脑</h2>
        <ul className="plain small">
          <li>系统：{info.platform}</li>
          <li>工作区：{info.workspace}</li>
          <li data-testid="ffmpeg-state">ffmpeg：{info.ffmpeg && info.ffprobe ? "已就绪" : "没找到（导入和导出会失败）"}</li>
          <li>语音识别模型：{info.models ? "已下载" : "第一次导入时自动下载（约 400 MB）"}</li>
          {info.home && <li>安装位置：{info.home}</li>}
        </ul>
      </section>
    </main>
  );
}
