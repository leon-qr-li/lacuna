import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { authApi, type AuthStatus } from "./api";
import { BusyLabel } from "../loading/Loading";
import { currentTheme, setTheme } from "../theme/theme";
import { lang, setLang, t } from "../../i18n";

type View = "login" | "register" | "forgot";
const MIN = 10;

/** Sign in / create account / reset password (design B: brand panel left, form right). */
export function AuthScreen({ status, onDone }: { status: AuthStatus; onDone: () => void }) {
  const [view, setView] = useState<View>(status.accounts ? "login" : "register");
  const [email, setEmail] = useState("");
  return (
    <div className="auth">
      <aside className="auth-art" aria-hidden="true">
        <div className="auth-logo">
          <i />
          LACUNA
        </div>
        <p className="auth-tag">
          {t("在留白处，听见电影。")}
          <small>{t("《洛城二三事》的剪辑工作台")}</small>
        </p>
        <div className="auth-wave">
          {BARS.map((h, i) => (
            <i key={i} style={{ height: `${h}%`, animationDelay: `${(i % 9) * 0.12}s` }} />
          ))}
        </div>
      </aside>
      <main className="auth-side">
        <Corner />
        <div className="auth-form">
          {view === "login" && <Login status={status} email={email} setEmail={setEmail} go={setView} onDone={onDone} />}
          {view === "register" && <Register status={status} email={email} setEmail={setEmail} go={setView} onDone={onDone} />}
          {view === "forgot" && <Forgot email={email} setEmail={setEmail} go={setView} onDone={onDone} />}
        </div>
      </main>
    </div>
  );
}

// a fixed "level meter" for the brand panel (same shape on every render)
const BARS = Array.from({ length: 46 }, (_, i) => 18 + Math.abs(Math.sin(i * 0.47 + 1) * Math.cos(i * 0.13)) * 82);

// each language is named in itself
const ZH = "中文"; // i18n-ignore

function Corner() {
  const [theme, setT] = useState(currentTheme());
  return (
    <div className="auth-corner">
      <button type="button" className="btn btn-outline btn-small" onClick={() => setLang(lang === "en" ? "zh" : "en")}>
        {lang === "en" ? ZH : "English"}
      </button>
      <button
        type="button"
        className="btn btn-outline btn-small"
        aria-label={theme === "dark" ? t("浅色") : t("深色")}
        onClick={() => {
          const next = theme === "dark" ? "light" : "dark";
          setTheme(next);
          setT(next);
        }}
      >
        {theme === "dark" ? "☀" : "☾"}
      </button>
    </div>
  );
}

interface FormProps {
  email: string;
  setEmail: (s: string) => void;
  go: (v: View) => void;
  onDone: () => void;
}

/** Runs `fn`, keeping the button busy and showing its error under the form. */
function useSubmit() {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setErr(null);
    try {
      await fn();
    } catch (e) {
      setErr(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  };
  return { busy, err, setErr, run };
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="auth-field">
      <span className="auth-label">
        {label}
        {hint && <em> · {hint}</em>}
      </span>
      {children}
    </label>
  );
}

function Password({ value, onChange, label, hint, autoComplete, testid }: {
  value: string;
  onChange: (s: string) => void;
  label: string;
  hint?: string;
  autoComplete: string;
  testid: string;
}) {
  const [show, setShow] = useState(false);
  return (
    <Field label={label} hint={hint}>
      <span className="auth-input">
        <input
          type={show ? "text" : "password"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          autoComplete={autoComplete}
          data-testid={testid}
          required
        />
        <button type="button" className="auth-eye" onClick={() => setShow(!show)}>
          {show ? t("隐藏") : t("显示")}
        </button>
      </span>
    </Field>
  );
}

function EmailField({ email, setEmail, autoFocus }: { email: string; setEmail: (s: string) => void; autoFocus?: boolean }) {
  return (
    <Field label={t("邮箱")}>
      <span className="auth-input">
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="email"
          autoFocus={autoFocus}
          data-testid="auth-email"
          required
        />
      </span>
    </Field>
  );
}

function strength(pw: string): [number, string] {
  if (pw.length < MIN) return [pw ? 1 : 0, t("太短")];
  const kinds = [/[a-z]/, /[A-Z]/, /\d/, /[^\w\s]/].filter((r) => r.test(pw)).length + (/\s/.test(pw) ? 1 : 0);
  const s = Math.min(4, 1 + (pw.length >= 14 ? 1 : 0) + (kinds >= 2 ? 1 : 0) + (kinds >= 3 || pw.length >= 20 ? 1 : 0));
  return [s, [t("太短"), t("太短"), t("一般"), t("好"), t("很好")][s]];
}

function Meter({ pw }: { pw: string }) {
  const [s, label] = strength(pw);
  return (
    <div className="auth-meter" aria-live="polite">
      {[1, 2, 3, 4].map((i) => (
        <i key={i} className={i <= s ? (s <= 1 ? "is-weak" : "is-on") : ""} />
      ))}
      <span>{t("密码强度：{s}", { s: label })}</span>
    </div>
  );
}

/** Six boxes over one real input (paste and SMS/email autofill work as usual). */
function CodeInput({ value, onChange }: { value: string; onChange: (s: string) => void }) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <div className="auth-code" onClick={() => ref.current?.focus()}>
      <input
        ref={ref}
        inputMode="numeric"
        autoComplete="one-time-code"
        maxLength={6}
        value={value}
        aria-label={t("验证码")}
        data-testid="auth-code"
        onChange={(e) => onChange(e.target.value.replace(/\D/g, "").slice(0, 6))}
      />
      {Array.from({ length: 6 }, (_, i) => (
        <span key={i} className={i === Math.min(value.length, 5) ? "is-cur" : ""}>
          {value[i] ?? ""}
        </span>
      ))}
    </div>
  );
}

/** "Send code" with a 60-second cooldown. */
function useCode(purpose: "register" | "reset") {
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [wait, setWait] = useState(0);
  useEffect(() => {
    if (wait <= 0) return;
    const id = setTimeout(() => setWait(wait - 1), 1000);
    return () => clearTimeout(id);
  }, [wait]);
  const send = async (email: string) => {
    await authApi.sendCode(email, purpose);
    setSentTo(email.trim());
    setWait(60);
  };
  return { sentTo, wait, send };
}

function Login({ status, email, setEmail, go, onDone }: FormProps & { status: AuthStatus }) {
  const [pw, setPw] = useState("");
  const [remember, setRemember] = useState(true);
  const { busy, err, run } = useSubmit();
  const submit = (e: FormEvent) => {
    e.preventDefault();
    run(async () => {
      await authApi.login(email, pw, remember);
      onDone();
    });
  };
  return (
    <form onSubmit={submit}>
      <h1>{t("欢迎回来")}</h1>
      <p className="auth-sub">{t("登录 LACUNA Studio，继续剪你的节目。")}</p>
      <EmailField email={email} setEmail={setEmail} autoFocus />
      <Password value={pw} onChange={setPw} label={t("密码")} autoComplete="current-password" testid="auth-password" />
      <div className="auth-row">
        <label className="auth-check">
          <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
          {t("30 天内记住我")}
        </label>
        <button type="button" className="auth-link" onClick={() => go("forgot")}>
          {t("忘记密码？")}
        </button>
      </div>
      {err && <p className="auth-err" role="alert">{err}</p>}
      <button className="auth-btn" disabled={busy}>
        <BusyLabel busy={busy} label={t("登录")} busyLabel={t("登录中…")} />
      </button>
      {status.allow_register && (
        <p className="auth-foot">
          {t("还没有账号？")}{" "}
          <button type="button" className="auth-link" onClick={() => go("register")}>
            {t("注册")}
          </button>
        </p>
      )}
      <p className="auth-note">
        <i />
        {t("密码在这台电脑上校验，断网也能登录。")}
      </p>
    </form>
  );
}

function Register({ status, email, setEmail, go, onDone }: FormProps & { status: AuthStatus }) {
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [code, setCode] = useState("");
  const { busy, err, setErr, run } = useSubmit();
  const c = useCode("register");
  const first = status.first;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (pw.length < MIN) return setErr(t("密码至少要 {n} 位", { n: MIN }));
    if (pw !== pw2) return setErr(t("两次输入的密码不一样"));
    if (!first && code.length !== 6) return setErr(t("先发验证码，再填邮件里的 6 位数字"));
    run(async () => {
      await authApi.register(email, pw, first ? null : code, true);
      onDone();
    });
  };
  return (
    <form onSubmit={submit}>
      <h1>{first ? t("创建你的账号") : t("创建账号")}</h1>
      <p className="auth-sub">
        {first
          ? t("这是这台电脑上的第一个账号，以后打开 LACUNA 用它登录。")
          : t("我们会给你的邮箱发一个 6 位验证码。")}
      </p>
      <EmailField email={email} setEmail={setEmail} autoFocus />
      <Password value={pw} onChange={setPw} label={t("密码")} hint={t("至少 {n} 位", { n: MIN })} autoComplete="new-password" testid="auth-password" />
      <Meter pw={pw} />
      <Password value={pw2} onChange={setPw2} label={t("确认密码")} autoComplete="new-password" testid="auth-password2" />
      {!first && (
        <>
          <div className="auth-label">{t("验证码")}</div>
          <CodeInput value={code} onChange={setCode} />
          <div className="auth-hint">
            <span>{c.sentTo ? t("已发送到 {email}", { email: c.sentTo }) : t("验证码会发到上面的邮箱")}</span>
            <button
              type="button"
              className="auth-link"
              disabled={busy || c.wait > 0 || !email}
              onClick={() => run(() => c.send(email))}
            >
              {c.wait > 0 ? t("重新发送（{n}s）", { n: c.wait }) : c.sentTo ? t("重新发送") : t("发送验证码")}
            </button>
          </div>
        </>
      )}
      {err && <p className="auth-err" role="alert">{err}</p>}
      <button className="auth-btn" disabled={busy}>
        <BusyLabel busy={busy} label={t("创建账号")} busyLabel={t("创建中…")} />
      </button>
      {status.accounts && (
        <p className="auth-foot">
          {t("已有账号？")}{" "}
          <button type="button" className="auth-link" onClick={() => go("login")}>
            {t("登录")}
          </button>
        </p>
      )}
      {first && (
        <p className="auth-note">
          <i />
          {t("密码只保存在这台电脑上（加密哈希），断网也能登录。")}
        </p>
      )}
    </form>
  );
}

function Forgot({ email, setEmail, go, onDone }: FormProps) {
  const [code, setCode] = useState("");
  const [pw, setPw] = useState("");
  const { busy, err, setErr, run } = useSubmit();
  const c = useCode("reset");
  const step = c.sentTo ? 2 : 1;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (step === 1) return run(() => c.send(email));
    if (code.length !== 6) return setErr(t("填邮件里的 6 位验证码"));
    if (pw.length < MIN) return setErr(t("密码至少要 {n} 位", { n: MIN }));
    run(async () => {
      await authApi.reset(email, code, pw);
      onDone();
    });
  };
  return (
    <form onSubmit={submit}>
      <h1>{t("重设密码")}</h1>
      <p className="auth-sub">
        {step === 1 ? t("输入注册时用的邮箱，我们发一个 6 位验证码给你。") : t("输入邮箱收到的验证码，再设一个新密码。")}
      </p>
      <ol className="auth-steps">
        <li className={step > 1 ? "is-done" : "is-on"}>
          <b>{step > 1 ? "✓" : "1"}</b>
          {t("邮箱")}
        </li>
        <li className={step === 2 ? "is-on" : ""}>
          <b>2</b>
          {t("验证码和新密码")}
        </li>
      </ol>
      {step === 1 ? (
        <EmailField email={email} setEmail={setEmail} autoFocus />
      ) : (
        <>
          <div className="auth-label">{t("验证码")}</div>
          <CodeInput value={code} onChange={setCode} />
          <div className="auth-hint">
            <span>{t("已发送到 {email}（没有这个账号就不会收到）", { email: c.sentTo ?? "" })}</span>
            <button type="button" className="auth-link" disabled={busy || c.wait > 0} onClick={() => run(() => c.send(email))}>
              {c.wait > 0 ? t("重新发送（{n}s）", { n: c.wait }) : t("重新发送")}
            </button>
          </div>
          <Password value={pw} onChange={setPw} label={t("新密码")} hint={t("至少 {n} 位", { n: MIN })} autoComplete="new-password" testid="auth-password" />
          <Meter pw={pw} />
        </>
      )}
      {err && <p className="auth-err" role="alert">{err}</p>}
      <button className="auth-btn" disabled={busy}>
        <BusyLabel
          busy={busy}
          label={step === 1 ? t("发送验证码") : t("保存并登录")}
          busyLabel={step === 1 ? t("发送中…") : t("保存中…")}
        />
      </button>
      <p className="auth-foot">
        <button type="button" className="auth-link" onClick={() => go("login")}>
          ← {t("返回登录")}
        </button>
      </p>
    </form>
  );
}
