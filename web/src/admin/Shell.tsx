// The admin's frame (decision 2026-10-24-admin-site): sign-in first, then a left sidebar (four groups), a top bar
// with 演示数据 / 中英 / 深浅色 and the session, the page, and on a phone a bottom bar for 待处理 · 反馈 · 申请 · 更多.
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { api, get, onSignedOut, onStepUp } from "./api";
import { lang, setLang, t } from "./i18n";
import { ROLE } from "./labels";
import type { Me, Overview } from "./types";
import { Avatar, Icon, isDemo, setDemo, toast, useDemo } from "./ui";
import { demoData } from "./demo";
import { createRoot } from "react-dom/client";
import { Home } from "./pages/Home";
import { FeedbackPage } from "./pages/Feedback";
import { HoursPage } from "./pages/Hours";
import { AccessPage } from "./pages/Access";
import { UsersPage } from "./pages/Users";
import { ShowsPage } from "./pages/Shows";
import { TrashPage } from "./pages/Trash";
import { AiPage } from "./pages/Ai";
import { GrowthPage } from "./pages/Growth";
import { SystemPage } from "./pages/System";
import { SettingsPage } from "./pages/Settings";
import { AuditPage } from "./pages/Audit";

export interface PageProps {
  me: Me;
  go: (path: string) => void;
}

interface Route {
  path: string;
  label: () => string;
  icon: string;
  count?: (o: Overview["todo"]) => number;
  render: (p: PageProps) => ReactNode;
}

const SECTIONS: { title: () => string; routes: Route[] }[] = [
  {
    title: () => t("工作"),
    routes: [
      { path: "/", label: () => t("首页"), icon: "home", render: (p) => <Home {...p} /> },
      { path: "/feedback", label: () => t("反馈"), icon: "inbox", count: (o) => o.fb, render: (p) => <FeedbackPage {...p} /> },
      { path: "/hours", label: () => t("时长申请"), icon: "clock", count: (o) => o.hours, render: (p) => <HoursPage {...p} /> },
      { path: "/access", label: () => t("邀请与申请"), icon: "mail", count: (o) => o.trial + o.collab, render: (p) => <AccessPage {...p} /> },
    ],
  },
  {
    title: () => t("管理"),
    routes: [
      { path: "/users", label: () => t("用户"), icon: "users", render: (p) => <UsersPage {...p} /> },
      { path: "/shows", label: () => t("节目与剧集"), icon: "mic", render: (p) => <ShowsPage {...p} /> },
      { path: "/trash", label: () => t("回收区"), icon: "trash", render: (p) => <TrashPage {...p} /> },
    ],
  },
  {
    title: () => t("数据"),
    routes: [
      { path: "/ai", label: () => t("AI 用量与成本"), icon: "spark", render: (p) => <AiPage {...p} /> },
      { path: "/growth", label: () => t("增长与留存"), icon: "chart", render: (p) => <GrowthPage {...p} /> },
      { path: "/system", label: () => t("系统健康"), icon: "pulse", render: (p) => <SystemPage {...p} /> },
    ],
  },
  {
    title: () => t("后台"),
    routes: [
      { path: "/settings", label: () => t("系统设置"), icon: "gear", render: (p) => <SettingsPage {...p} /> },
      { path: "/audit", label: () => t("操作日志"), icon: "log", render: (p) => <AuditPage {...p} /> },
    ],
  },
];
const ROUTES = SECTIONS.flatMap((s) => s.routes);
const PHONE_TABS = ["/", "/feedback", "/access", "/hours"];

const THEME = "lacuna.admin.theme";
// each language named in itself, whatever the interface language
const ZH_SHORT = "中"; // i18n-ignore
const ZH_NAME = "中文"; // i18n-ignore
export function applyTheme(th?: "light" | "dark") {
  let v = th;
  if (!v) {
    try {
      v = localStorage.getItem(THEME) === "dark" ? "dark" : "light";
    } catch {
      v = "light";
    }
  } else {
    try {
      localStorage.setItem(THEME, v);
    } catch {
      /* private mode */
    }
  }
  document.documentElement.dataset.theme = v;
  return v;
}

function usePath(): [string, (p: string) => void] {
  const [path, setPath] = useState(location.pathname);
  useEffect(() => {
    const f = () => setPath(location.pathname);
    window.addEventListener("popstate", f);
    return () => window.removeEventListener("popstate", f);
  }, []);
  const go = useCallback((p: string) => {
    const [pathname] = p.split("?");
    if (p !== location.pathname + location.search) history.pushState(null, "", p);
    setPath(pathname);
    document.querySelector(".a-content")?.scrollTo(0, 0);
  }, []);
  return [path, go];
}

export function Admin() {
  const [me, setMe] = useState<Me | null | undefined>(undefined);
  const demo = useDemo();
  useEffect(() => {
    get<Me>("/api/admin/auth/me").then(setMe, () => setMe(null));
    onSignedOut(() => setMe(null));
    onStepUp(stepUp);
  }, []);
  if (me === undefined) return <div className="a-boot" aria-busy="true" />;
  if (me === null && !demo) return <Login onIn={setMe} />;
  return <Frame me={me ?? (demoData("/api/admin/auth/me") as Me)} signOut={() => setMe(null)} />;
}

function Frame({ me, signOut }: { me: Me; signOut: () => void }) {
  const [path, go] = usePath();
  const demo = useDemo();
  const [todo, setTodo] = useState<Overview["todo"]>({ fb: 0, hours: 0, trial: 0, collab: 0 });
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme as "light" | "dark");
  const [menu, setMenu] = useState(false);
  useEffect(() => {
    const load = () => {
      if (isDemo()) return setTodo((demoData("/api/admin/overview") as Overview).todo);
      get<Overview>("/api/admin/overview").then((o) => setTodo(o.todo), () => undefined);
    };
    load();
    const id = window.setInterval(load, 60_000);
    return () => window.clearInterval(id);
  }, [demo, path]);
  const route = ROUTES.find((r) => r.path === path) ?? ROUTES[0];
  useEffect(() => {
    document.title = `${route.label()} · LACUNA Admin`;
    setMenu(false);
  }, [route]);
  const left = Math.max(0, Math.round((me.exp - Date.now() / 1000) / 3600));
  const out = async () => {
    try {
      await api("POST", "/api/admin/auth/logout");
    } catch {
      /* gone already */
    }
    setDemo(false);
    signOut();
  };
  const nav = (
    <nav className="a-nav" aria-label={t("后台导航")}>
      {SECTIONS.map((s) => (
        <div key={s.title()} className="a-nav-sec">
          <div className="a-nav-h">{s.title()}</div>
          {s.routes.map((r) => {
            const n = r.count?.(todo) ?? 0;
            return (
              <a
                key={r.path}
                href={r.path}
                aria-current={r === route ? "page" : undefined}
                onClick={(e) => {
                  e.preventDefault();
                  go(r.path);
                }}
                data-testid={`nav-${r.path.slice(1) || "home"}`}
              >
                <Icon name={r.icon} />
                <span>{r.label()}</span>
                {r.count && <span className={`ct${n ? "" : " z"}`}>{n}</span>}
              </a>
            );
          })}
        </div>
      ))}
    </nav>
  );
  return (
    <div className={`a-app${demo ? " is-demo" : ""}`}>
      <aside className={`a-side${menu ? " open" : ""}`}>
        <div className="a-brand">
          <span className="mk" aria-hidden="true" />
          <div>
            <b>LACUNA Admin</b>
            <span>{location.host}</span>
          </div>
        </div>
        {nav}
        <div className="a-me">
          <Avatar name={me.name || me.email} />
          <div className="who">
            <b>{me.name || me.email}</b>
            <span>
              {ROLE[me.role]?.()} · {t("{n} 小时后退出", { n: left })}
            </span>
          </div>
          <button type="button" className="a-ib" onClick={out} aria-label={t("退出后台")} title={t("退出后台")} data-testid="logout">
            <Icon name="out" />
          </button>
        </div>
      </aside>
      {menu && <div className="a-side-scrim" onClick={() => setMenu(false)} />}
      <div className="a-main">
        <header className="a-top">
          <button type="button" className="a-ib a-menu" onClick={() => setMenu(true)} aria-label={t("菜单")}>
            <Icon name="menu" />
          </button>
          <b className="a-top-title">{route.label()}</b>
          <span className="spacer" />
          <div className={`a-tg${demo ? " demo" : ""}`} role="group" aria-label={t("数据")}>
            <button type="button" aria-pressed={!demo} onClick={() => setDemo(false)} data-testid="data-real">
              {t("真实数据")}
            </button>
            <button type="button" aria-pressed={demo} onClick={() => setDemo(true)} data-testid="data-demo" title={t("演示数据只用来看，不会保存任何操作")}>
              {t("演示数据")}
            </button>
          </div>
          <div className="a-tg" role="group" aria-label={t("语言")}>
            <button type="button" aria-pressed={lang === "zh"} onClick={() => lang !== "zh" && setLang("zh")}>
              {ZH_SHORT}
            </button>
            <button type="button" aria-pressed={lang === "en"} onClick={() => lang !== "en" && setLang("en")} data-testid="lang-en">
              EN
            </button>
          </div>
          <button
            type="button"
            className="a-ib"
            onClick={() => setTheme(applyTheme(theme === "dark" ? "light" : "dark"))}
            aria-label={theme === "dark" ? t("浅色") : t("深色")}
            title={theme === "dark" ? t("浅色") : t("深色")}
            data-testid="theme"
          >
            <Icon name={theme === "dark" ? "sun" : "moon"} />
          </button>
        </header>
        {demo && (
          <div className="a-demo-bar" role="status">
            {t("正在看演示数据：页面上的数字和人都是编的，任何操作都不会保存。")}
            <button type="button" className="a-btn sm" onClick={() => setDemo(false)}>
              {t("回到真实数据")}
            </button>
          </div>
        )}
        <main className="a-content" key={`${route.path}-${demo}`}>
          {route.render({ me, go })}
        </main>
        <nav className="a-tabbar" aria-label={t("手机导航")}>
          {PHONE_TABS.map((p) => {
            const r = ROUTES.find((x) => x.path === p)!;
            const n = r.count?.(todo) ?? 0;
            return (
              <button key={p} type="button" aria-current={r === route ? "page" : undefined} onClick={() => go(p)}>
                <Icon name={r.icon} size={20} />
                <span>{p === "/" ? t("待处理") : p === "/access" ? t("申请") : p === "/hours" ? t("时长") : r.label()}</span>
                {n > 0 && <i>{n}</i>}
              </button>
            );
          })}
          <button type="button" onClick={() => setMenu(true)}>
            <Icon name="menu" size={20} />
            <span>{t("更多")}</span>
          </button>
        </nav>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ sign-in
function Login({ onIn }: { onIn: (m: Me) => void }) {
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      onIn(await api<Me>("POST", "/api/admin/auth/login", { email, password: pw, code }));
    } catch (x) {
      setErr((x as Error).message);
      setCode("");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="a-login">
      <form className="a-lbox" onSubmit={submit}>
        <div className="a-row">
          <span className="mk" aria-hidden="true" />
          <div>
            <b>LACUNA Admin</b>
            <div className="a-muted small">{location.host}</div>
          </div>
        </div>
        <h1>{t("登录后台")}</h1>
        <div className="a-card a-login-card">
          <label className="a-lbl">
            {t("邮箱")}
            <input className="a-inp" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} data-testid="login-email" />
          </label>
          <label className="a-lbl">
            {t("密码")}
            <input className="a-inp" type="password" autoComplete="current-password" required value={pw} onChange={(e) => setPw(e.target.value)} data-testid="login-password" />
          </label>
          <label className="a-lbl">
            {t("验证码")}
            <input
              className="a-inp mono"
              inputMode="numeric"
              autoComplete="one-time-code"
              required
              maxLength={12}
              placeholder={t("验证器 App 上的 6 位数字")}
              value={code}
              onChange={(e) => setCode(e.target.value.trim())}
              data-testid="login-code"
            />
          </label>
          {err && (
            <p className="a-error" role="alert" data-testid="login-error">
              {err}
            </p>
          )}
          <button type="submit" className="a-btn pri big" disabled={busy || !email || !pw || !code} data-testid="login-submit">
            {busy ? t("正在登录…") : t("进入后台")}
          </button>
        </div>
        <p className="a-muted small">{t("后台登录 8 小时后自动退出，不能「记住我」。每次登录都会给站长发提醒邮件。主站的登录状态在这里无效。")}</p>
        <div className="a-row">
          <button type="button" className="a-btn ghost sm" onClick={() => setDemo(true)} data-testid="login-demo">
            {t("先看演示数据")}
          </button>
          <span className="spacer" />
          <button type="button" className="a-btn ghost sm" onClick={() => setLang(lang === "en" ? "zh" : "en")}>
            {lang === "en" ? ZH_NAME : "English"}
          </button>
        </div>
      </form>
    </div>
  );
}

// ------------------------------------------------------------------ 再输一次验证码
let stepping: Promise<boolean> | null = null;
function stepUp(): Promise<boolean> {
  if (stepping) return stepping;
  stepping = new Promise<boolean>((resolve) => {
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    const done = (ok: boolean) => {
      root.unmount();
      host.remove();
      stepping = null;
      resolve(ok);
    };
    root.render(<StepUp done={done} />);
  });
  return stepping;
}

function StepUp({ done }: { done: (ok: boolean) => void }) {
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const send = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await api("POST", "/api/admin/auth/stepup", { code });
      toast(t("验证通过，15 分钟内不用再输"));
      done(true);
    } catch (x) {
      setErr((x as Error).message);
      setCode("");
      setBusy(false);
    }
  };
  return (
    <div className="a-scrim center">
      <form className="a-modal" role="dialog" aria-modal="true" aria-label={t("输入验证码")} onSubmit={send} data-testid="stepup">
        <h3>
          <Icon name="lock" /> {t("输入验证码")}
        </h3>
        <p>{t("这一步会改动账号或数据，需要再确认一次。打开验证器 App，输入 6 位数字。15 分钟内不会再问。")}</p>
        <input
          className="a-inp otp"
          inputMode="numeric"
          autoComplete="one-time-code"
          autoFocus
          maxLength={6}
          value={code}
          onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
          aria-label={t("验证码")}
          data-testid="stepup-code"
        />
        {err && <p className="a-error">{err}</p>}
        <div className="a-row end">
          <button type="button" className="a-btn" onClick={() => done(false)}>
            {t("取消")}
          </button>
          <button type="submit" className="a-btn pri" disabled={busy || code.length !== 6} data-testid="stepup-ok">
            {t("确认")}
          </button>
        </div>
      </form>
    </div>
  );
}
