import { useCallback, useEffect, useState } from "react";
import type { AppInfo } from "./api";
import { settingsApi } from "./api";
import { navCurrent } from "../registry";
import { ThemeSetting } from "../theme/ThemeSetting";
import { AccountCard } from "../auth/AccountCard";
import { SpacesCard } from "../spaces/SpacesCard";
import { SystemTermsCard } from "../transcript-fix/SystemTermsCard";
import { t } from "../../i18n";
import { PageLoading } from "../loading/Loading";

const KEY_SOURCE: Record<string, string> = {
  env: t("环境变量"),
  "registry-user": t("Windows 用户环境变量"),
  "registry-machine": t("Windows 系统环境变量"),
  keychain: t("macOS 钥匙串"),
  file: t("本机文件"),
};

/** Top-bar link to 设置. */
export function SettingsLink() {
  return (
    <a className="btn btn-outline row" href="#/settings" aria-current={navCurrent("settings")}>
      {t("设置")}
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

  const saveKey = () =>
    run("key", async () => {
      await settingsApi.saveApiKey(key.trim());
      setKey("");
      setMsg(t("已保存。重启 LACUNA 后生效。"));
      load();
    });

  if (!info) return err ? <p className="error pad">{err}</p> : <PageLoading label={t("正在打开设置…")} />;
  return (
    <main className="home settings">
      <h1>{t("设置")}</h1>
      {msg && (
        <p className="card" role="status">
          {msg}
        </p>
      )}
      {err && <p className="error">{err}</p>}

      <ThemeSetting />

      <section className="card" aria-label={t("版本")}>
        <div className="card-head">
          <h2>{t("版本")}</h2>
          <span className="badge" data-testid="app-version">
            {info.cloud ? info.version.slice(0, 7) : info.version === "dev" ? t("开发版") : info.version}
          </span>
        </div>
        {info.cloud && <p className="muted small" data-testid="cloud-auto-update">{t("新版本测试通过后会自动上线，不用手动更新。")}</p>}
      </section>

      <section className="card" aria-label={t("AI 密钥")}>
        <div className="card-head">
          <h2>{t("AI 密钥")}</h2>
          <span className={info.key.present ? "badge badge-confirmed" : "badge badge-unknown"} data-testid="key-state">
            {info.key.present ? t("已设置（{p0}）", { p0: KEY_SOURCE[info.key.source ?? ""] ?? info.key.source }) : t("没有设置")}
          </span>
        </div>
        {info.cloud ? (
          <p className="muted small">{t("AI 密钥由服务器统一管理，只保存在服务器上，不会显示出来。")}</p>
        ) : (<>
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
        </>)}
      </section>

      <AccountCard />
      <SpacesCard />
      <SystemTermsCard />

      {!info.cloud && (
      <section className="card" aria-label={t("这台电脑")}>
        <h2>{t("这台电脑")}</h2>
        <ul className="plain small">
          <li>{t("系统：")}{info.platform}</li>
          <li>{t("工作区：")}{info.workspace}</li>
          <li data-testid="ffmpeg-state">ffmpeg：{info.ffmpeg && info.ffprobe ? t("已就绪") : t("没找到（导入和导出会失败）")}</li>
          <li>{t("语音识别模型：")}{info.models ? t("已下载") : t("第一次导入时自动下载（约 400 MB）")}</li>
        </ul>
      </section>
      )}
    </main>
  );
}
