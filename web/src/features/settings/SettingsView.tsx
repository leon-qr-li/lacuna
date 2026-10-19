import { useCallback, useEffect, useState } from "react";
import type { AppInfo } from "./api";
import { settingsApi } from "./api";
import { navCurrent } from "../registry";
import { ThemeSetting } from "../theme/ThemeSetting";
import { AccountCard } from "../auth/AccountCard";
import { SpacesCard } from "../spaces/SpacesCard";
import { joinList, t } from "../../i18n";
import { BusyLabel, JobProgress, PageLoading } from "../loading/Loading";

const KEY_SOURCE: Record<string, string> = {
  env: t("环境变量"),
  "registry-user": t("Windows 用户环境变量"),
  "registry-machine": t("Windows 系统环境变量"),
  keychain: t("macOS 钥匙串"),
  file: t("本机文件"),
};

/** Polls /api/app until the server has gone down and answers again (a plain restart). */
async function waitForRestart(): Promise<void> {
  const end = Date.now() + 10 * 60_000; // first install of new packages can take a few minutes
  let wentDown = false;
  while (Date.now() < end) {
    await new Promise((r) => setTimeout(r, 1500));
    try {
      await settingsApi.appInfo();
      if (wentDown) return;
    } catch {
      wentDown = true;
    }
  }
}

/** After an update: polls until the launcher has logged how it went (updated, or rolled back).
 * The new version answers a moment before the log is written, and a rollback keeps the old version,
 * so neither the version alone nor the server coming back is enough. */
async function waitForUpdate(target: string, lastAt: string | undefined): Promise<void> {
  const end = Date.now() + 10 * 60_000;
  while (Date.now() < end) {
    await new Promise((r) => setTimeout(r, 1500));
    try {
      const last = (await settingsApi.appInfo()).update.last_update;
      if (last && last.to === target && last.at !== lastAt) return;
    } catch {
      // restarting
    }
  }
}

/** Top-bar link to 设置, with a dot when an update is waiting. */
export function SettingsLink() {
  const [update, setUpdate] = useState(false);
  useEffect(() => {
    settingsApi
      .appInfo()
      .then((i) => setUpdate(i.update.available))
      .catch(() => setUpdate(false));
  }, []);
  return (
    <a className="btn btn-outline row" href="#/settings" aria-current={navCurrent("settings")}>
      {t("设置")}{update ? t(" · 有新版本") : ""}
    </a>
  );
}

export function SettingsView() {
  const [info, setInfo] = useState<AppInfo | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [key, setKey] = useState("");

  const load = useCallback(() => settingsApi.appInfo().then(setInfo).catch((e) => setErr(String(e.message ?? e))), []);
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

  const check = () => run("check", async () => setInfo(await settingsApi.checkUpdate()));
  const prepare = () => run("prepare", async () => setInfo(await settingsApi.prepareUpdate()));
  const apply = () =>
    run("apply", async () => {
      const lastAt = info!.update.last_update?.at;
      const r = await settingsApi.applyUpdate();
      setMsg(t("正在更新并重启，页面会自己刷新…"));
      await waitForUpdate(r.version, lastAt);
      window.location.reload();
    });
  const saveKey = () =>
    run("key", async () => {
      const r = await settingsApi.saveApiKey(key.trim());
      setKey("");
      if (r.restarting) {
        setMsg(t("已保存，正在重启让它生效…"));
        await waitForRestart();
        window.location.reload();
      } else {
        setMsg(t("已保存。重启 LACUNA 后生效。"));
        load();
      }
    });

  if (!info) return err ? <p className="error pad">{err}</p> : <PageLoading label={t("正在打开设置…")} />;
  const u = info.update;
  return (
    <main className="home settings">
      <h1>{t("设置")}</h1>
      {msg && (
        <p className="card" role="status">
          <BusyLabel busy={busy === "apply" || busy === "key"} label={msg} />
        </p>
      )}
      {err && <p className="error">{err}</p>}

      <ThemeSetting />

      <section className="card" aria-label={t("版本")}>
        <div className="card-head">
          <h2>{t("版本")}</h2>
          <span className="badge" data-testid="app-version">
            {info.installed ? info.version : t("开发版")}
          </span>
        </div>
        {!info.installed && <p className="muted small">{t("这是从源码直接运行的开发版，不在 App 里更新。")}</p>}
        {u.last_update && (
          <p className={u.last_update.ok ? "muted small" : "error"}>
            {t("上次更新（{at}）：{message}", { at: u.last_update.at, message: u.last_update.message })}
          </p>
        )}
        {info.installed && (
          <>
            {u.available ? (
              <div data-testid="update-available">
                <p>
                  {t("有新版本")} <strong>{u.latest}</strong>
                </p>
                {u.notes && <pre className="notes">{u.notes}</pre>}
                {job?.state === "running" ? (
                  <JobProgress flat title={t("正在下载 {version}", { version: u.latest })} progress={job.progress ?? 0} testId="update-download" />
                ) : job?.state === "ready" ? (
                  <>
                    {info.busy.length > 0 && <p className="muted small">{t("{tasks}还在进行，做完才能更新。", { tasks: joinList(info.busy) })}</p>}
                    <button className="btn btn-primary" disabled={!!busy || info.busy.length > 0} onClick={apply}>
                      {t("更新并重启")}
                    </button>
                    <p className="muted small">{t("大约一两分钟。正在编辑的内容都已经自动保存。新版本起不来会自动回到现在的版本。")}</p>
                  </>
                ) : (
                  <>
                    {job?.state === "error" && <p className="error">{job.error}</p>}
                    <button className="btn btn-primary" disabled={!!busy} onClick={prepare}>
                      {t("下载新版本")}
                    </button>
                  </>
                )}
              </div>
            ) : (
              <p className="muted">{u.error ?? (u.latest ? t("已经是最新版本。") : t("还没检查过更新。"))}</p>
            )}
            <button className="btn btn-outline" disabled={!!busy} onClick={check}>
              <BusyLabel busy={busy === "check"} label={t("检查更新")} busyLabel={t("检查中…")} />
            </button>
          </>
        )}
      </section>

      <section className="card" aria-label={t("AI 密钥")}>
        <div className="card-head">
          <h2>{t("AI 密钥")}</h2>
          <span className={info.key.present ? "badge badge-confirmed" : "badge badge-unknown"} data-testid="key-state">
            {info.key.present ? t("已设置（{p0}）", { p0: KEY_SOURCE[info.key.source ?? ""] ?? info.key.source }) : t("没有设置")}
          </span>
        </div>
        <p className="muted small">
          {info.platform === "macOS" ? t("AI 第一刀、聊天修改、发布资料要用它。只保存在这台电脑上（钥匙串），不会显示出来。") : t("AI 第一刀、聊天修改、发布资料要用它。只保存在这台电脑上，不会显示出来。")}
        </p>
        <div className="row gap">
          <input
            className="grow"
            type="password"
            autoComplete="off"
            placeholder={t("粘贴 AI 密钥")}
            aria-label="API key"
            value={key}
            onChange={(e) => setKey(e.target.value)}
          />
          <button className="btn btn-outline" disabled={!!busy || key.trim().length < 20} onClick={saveKey}>
            {info.key.present ? t("换一个") : t("保存")}
          </button>
        </div>
      </section>

      <AccountCard />
      <SpacesCard />

      <section className="card" aria-label={t("这台电脑")}>
        <h2>{t("这台电脑")}</h2>
        <ul className="plain small">
          <li>{t("系统：")}{info.platform}</li>
          <li>{t("工作区：")}{info.workspace}</li>
          <li data-testid="ffmpeg-state">ffmpeg：{info.ffmpeg && info.ffprobe ? t("已就绪") : t("没找到（导入和导出会失败）")}</li>
          <li>{t("语音识别模型：")}{info.models ? t("已下载") : t("第一次导入时自动下载（约 400 MB）")}</li>
          {info.home && <li>{t("安装位置：")}{info.home}</li>}
        </ul>
      </section>
    </main>
  );
}
