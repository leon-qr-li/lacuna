import { useCallback, useEffect, useState } from "react";
import type { AppInfo } from "./api";
import { settingsApi } from "./api";
import { navCurrent } from "../registry";
import { ThemeSetting } from "../theme/ThemeSetting";
import { MailCard, MembersCard, SecurityCard, useAuthStatus } from "../auth/AccountCard";
import { SpacesCard } from "../spaces/SpacesCard";
import { HabitsCard } from "../habits/HabitsCard";
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

type Section = "general" | "edit" | "projects" | "account" | "members" | "mail" | "ai";
const SECTIONS: { id: Section; group: "me" | "admin"; label: string; about: string }[] = [
  { id: "general", group: "me", label: t("通用"), about: t("界面主题、语言和版本。") },
  { id: "edit", group: "me", label: t("剪辑习惯"), about: t("你平时下手多重，每个项目都按这个来。") },
  { id: "projects", group: "me", label: t("我的项目"), about: t("你建的和受邀加入的项目。") },
  { id: "account", group: "me", label: t("账号与安全"), about: t("登录、密码、两步验证和登录过的设备。") },
  { id: "members", group: "admin", label: t("成员与邀请"), about: t("邀请新账号、管理成员角色。") },
  { id: "mail", group: "admin", label: t("邮件发件人"), about: t("邀请邮件和验证码从哪个地址发出。") },
  { id: "ai", group: "admin", label: t("AI 与专有名词"), about: t("AI 密钥，以及所有项目的文字稿都按它校对的专有名词。") },
];
const sectionFromHash = (): Section => {
  const m = /^#\/settings\/([\w-]+)/.exec(window.location.hash)?.[1];
  return SECTIONS.some((x) => x.id === m) ? (m as Section) : "general";
};

/**
 * 设置 (Leon 2026-10-20, design C): a left side nav in two groups, 个人 (everyone) and 管理 (only admins: members
 * and invites, the mail sender, the AI key and the system terms), one section at a time at #/settings/<section>.
 */
export function SettingsView() {
  const [info, setInfo] = useState<AppInfo | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [key, setKey] = useState("");
  const [section, setSection] = useState<Section>(sectionFromHash);
  const auth = useAuthStatus();

  const load = useCallback(() => settingsApi.appInfo().then(setInfo).catch((e) => setErr(String(e.message ?? e))), []);
  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    const on = () => setSection(sectionFromHash());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);

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

  if (!info || !auth.loaded) return err ? <p className="error pad">{err}</p> : <PageLoading label={t("正在打开设置…")} />;
  const st = auth.st?.email && auth.st.role ? auth.st : null; // null: no sign-in (a local copy), the one user is its admin
  const admin = !st || st.role !== "member";
  const shown = SECTIONS.filter((x) => {
    if (x.id === "account" || x.id === "members") return !!st && (x.id === "account" || admin);
    if (x.id === "mail") return !!st && st.role === "owner" && !!st.mail;
    return x.group === "me" || admin;
  });
  const cur = shown.find((x) => x.id === section) ?? shown[0];

  const navGroup = (group: "me" | "admin") => {
    const items = shown.filter((x) => x.group === group);
    if (!items.length) return null;
    return (
      <div className="set-nav-group" role="group" aria-label={group === "me" ? t("个人") : t("管理")}>
        <div className="set-nav-label">
          {group === "me" ? t("个人") : t("管理")}
          {group === "admin" && <span className="set-nav-badge">{t("仅管理员")}</span>}
        </div>
        {items.map((x) => (
          <a key={x.id} className="set-nav-item" href={`#/settings/${x.id}`} aria-current={cur.id === x.id ? "page" : undefined} data-testid={`settings-nav-${x.id}`}>
            {x.label}
          </a>
        ))}
      </div>
    );
  };

  return (
    <main className="home settings">
      <h1>{t("设置")}</h1>
      <div className="set-layout">
        <nav className="set-nav" aria-label={t("设置")}>
          {navGroup("me")}
          {navGroup("admin")}
        </nav>
        <div className="set-main" data-testid={`settings-${cur.id}`}>
          <div className="set-head">
            <h2>{cur.label}</h2>
            <p className="muted small">{cur.about}</p>
          </div>
          {msg && (
            <p className="card" role="status">
              {msg}
            </p>
          )}
          {err && <p className="error">{err}</p>}

          {cur.id === "general" && (
            <>
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
              {!info.cloud && (
                <section className="card" aria-label={t("这台电脑")}>
                  <h2>{t("这台电脑")}</h2>
                  <ul className="plain small">
                    <li>{t("系统：")}{info.platform}</li>
                    <li>{t("项目：")}{info.workspace}</li>
                    <li data-testid="ffmpeg-state">ffmpeg：{info.ffmpeg && info.ffprobe ? t("已就绪") : t("没找到（导入和导出会失败）")}</li>
                    <li>{t("语音识别模型：")}{info.models ? t("已下载") : t("第一次导入时自动下载（约 400 MB）")}</li>
                  </ul>
                </section>
              )}
            </>
          )}
          {cur.id === "edit" && <HabitsCard />}
          {cur.id === "projects" && <SpacesCard />}
          {cur.id === "account" && st && <SecurityCard st={st} setSt={auth.setSt} />}
          {cur.id === "members" && st && <MembersCard me={st.email!} role={st.role!} />}
          {cur.id === "mail" && st && <MailCard st={st} setSt={auth.setSt} />}
          {cur.id === "ai" && (
            <>
              <section className="card" aria-label={t("AI 密钥")}>
                <div className="card-head">
                  <h2>{t("AI 密钥")}</h2>
                  <span className={info.key.present ? "badge badge-confirmed" : "badge badge-unknown"} data-testid="key-state">
                    {info.key.present ? t("已设置（{p0}）", { p0: KEY_SOURCE[info.key.source ?? ""] ?? info.key.source }) : t("没有设置")}
                  </span>
                </div>
                {info.cloud ? (
                  <p className="muted small">{t("AI 密钥由服务器统一管理，只保存在服务器上，不会显示出来。")}</p>
                ) : (
                  <>
                    <p className="muted small">
                      {info.platform === "macOS"
                        ? t("AI 第一刀、聊天修改、发布资料要用它。只保存在这台电脑上（钥匙串），不会显示出来。")
                        : t("AI 第一刀、聊天修改、发布资料要用它。只保存在这台电脑上，不会显示出来。")}
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
                  </>
                )}
              </section>
              <SystemTermsCard />
            </>
          )}
        </div>
      </div>
    </main>
  );
}
