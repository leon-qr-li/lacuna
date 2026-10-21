import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { authApi, type AuthStatus, type Step } from "./api";
import { CodeInput, RecoveryCodes, SecondFactor, TwoStepQR } from "./TwoStep";
import { Turnstile } from "./Turnstile";
import { BusyLabel } from "../loading/Loading";
import { currentTheme, setTheme } from "../theme/theme";
import { lang, langChosen, setLang, t } from "../../i18n";

type View =
  | { v: "login" }
  | { v: "first" }
  | { v: "invite"; token: string }
  | { v: "forgot" }
  | { v: "ask" }
  | { v: "code"; ticket: string; email: string }
  | { v: "enroll"; ticket: string; email: string; secret: string; uri: string }
  | { v: "saved"; email: string; codes: string[] };
const MIN = 10;

/** `/invite/<token>`: the link in an invite email (in the path: Cloudflare Access's sign-in drops a
 *  #fragment; links sent before that were `#/invite/<token>` and still work). */
export function inviteToken(): string | null {
  const m = /^\/invite\/([\w-]{20,})\/?$/.exec(window.location.pathname) ?? /^#\/invite\/([\w-]{20,})$/.exec(window.location.hash);
  return m ? m[1] : null;
}

/** Leaves the invite link for the app's home (剧集). */
export function dropInvite() {
  window.history.replaceState(null, "", "/#/");
}

/** Sign in (password, then the two-step code), the owner's first account, sign-up from an invite link,
 *  reset password, two-step setup and recovery codes (design B: brand panel left, form right). */
export function AuthScreen({ status, onDone }: { status: AuthStatus; onDone: () => void }) {
  const [view, setView] = useState<View>(() => {
    const token = inviteToken();
    if (token) return { v: "invite", token };
    return status.accounts ? { v: "login" } : { v: "first" };
  });
  const [email, setEmail] = useState("");
  /** what a sign-in step answered: signed in, or the next screen */
  const next = (s: Step, who: string) => {
    if (s.step === "2fa") setView({ v: "code", ticket: s.ticket, email: who });
    else if (s.step === "enroll") setView({ v: "enroll", ticket: s.ticket, email: who, secret: s.secret, uri: s.uri });
    else if (s.recovery?.length) setView({ v: "saved", email: who, codes: s.recovery });
    else onDone();
  };
  const go = (v: "login" | "forgot" | "ask") => {
    if (inviteToken()) dropInvite();
    setView({ v });
  };
  const p = { status, email, setEmail, go, next };
  return (
    <div className="auth">
      <aside className="auth-art" aria-hidden="true">
        <div className="auth-logo">
          <i />
          LACUNA
        </div>
        <p className="auth-tag">
          {SLOGAN}
          <small>{t("从录音到发布，一个工作台。")}</small>
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
          {view.v === "login" && <Login {...p} />}
          {view.v === "first" && <First {...p} />}
          {view.v === "invite" && <FromInvite {...p} token={view.token} />}
          {view.v === "forgot" && <Forgot {...p} />}
          {view.v === "ask" && <AskAccess {...p} />}
          {view.v === "code" && <Code {...p} ticket={view.ticket} who={view.email} />}
          {view.v === "enroll" && <Enroll {...p} view={view} />}
          {view.v === "saved" && (
            <>
              <h1>{t("保存恢复码")}</h1>
              <p className="auth-sub">
                {t("手机丢了或不在身边时，用其中一个代替 6 位数字登录。每个只能用一次，而且只显示这一次。")}
              </p>
              <RecoveryCodes codes={view.codes} email={view.email} onDone={onDone} doneLabel={t("进入 LACUNA")} />
            </>
          )}
        </div>
      </main>
    </div>
  );
}

// the brand line is English in both interface languages (Leon 2026-10-17)
const SLOGAN = "Mind the gaps. Keep the voice.";

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

interface FormProps {
  status: AuthStatus;
  email: string;
  setEmail: (s: string) => void;
  go: (v: "login" | "forgot" | "ask") => void;
  next: (s: Step, who: string) => void;
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

/** "Send code" with a 60-second cooldown (password reset). */
function useCode() {
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [wait, setWait] = useState(0);
  useEffect(() => {
    if (wait <= 0) return;
    const id = setTimeout(() => setWait(wait - 1), 1000);
    return () => clearTimeout(id);
  }, [wait]);
  const send = async (email: string) => {
    await authApi.sendCode(email);
    setSentTo(email.trim());
    setWait(60);
  };
  return { sentTo, wait, send };
}

function Err({ err }: { err: string | null }) {
  return err ? (
    <p className="auth-err" role="alert">
      {err}
    </p>
  ) : null;
}

function Login({ status, email, setEmail, go, next }: FormProps) {
  const [pw, setPw] = useState("");
  const [remember, setRemember] = useState(true);
  const [human, setHuman] = useState<string | null>(null);
  const [tries, setTries] = useState(0);
  const { busy, err, run } = useSubmit();
  const submit = (e: FormEvent) => {
    e.preventDefault();
    run(async () => {
      try {
        next(await authApi.login(email, pw, remember, human), email.trim().toLowerCase());
      } finally {
        if (status.turnstile) setTries((n) => n + 1); // a token works once
      }
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
      <Turnstile siteKey={status.turnstile} onToken={setHuman} nonce={tries} />
      <Err err={err} />
      <button className="auth-btn" disabled={busy || (!!status.turnstile && !human)}>
        <BusyLabel busy={busy} label={t("登录")} busyLabel={t("登录中…")} />
      </button>
      <p className="auth-foot">
        {t("还没有账号？LACUNA 目前仅限邀请。")}{" "}
        <button type="button" className="auth-link" onClick={() => go("ask")} data-testid="auth-ask">
          {t("申请试用")} →
        </button>
      </p>
      {!status.cloud && (
        <p className="auth-note">
          <i />
          {t("密码在这台电脑上校验，断网也能登录。")}
        </p>
      )}
    </form>
  );
}

function NewPassword({ pw, setPw, pw2, setPw2 }: { pw: string; setPw: (s: string) => void; pw2: string; setPw2: (s: string) => void }) {
  return (
    <>
      <Password value={pw} onChange={setPw} label={t("密码")} hint={t("至少 {n} 位", { n: MIN })} autoComplete="new-password" testid="auth-password" />
      <Meter pw={pw} />
      <Password value={pw2} onChange={setPw2} label={t("确认密码")} autoComplete="new-password" testid="auth-password2" />
    </>
  );
}

function checkNew(pw: string, pw2: string): string | null {
  if (pw.length < MIN) return t("密码至少要 {n} 位", { n: MIN });
  if (pw !== pw2) return t("两次输入的密码不一样");
  return null;
}

/** The owner's account, on the first run (in the cloud also the setup code from the server). */
function First({ status, email, setEmail, next }: FormProps) {
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [setup, setSetup] = useState("");
  const { busy, err, setErr, run } = useSubmit();
  useEffect(() => {
    if (status.owner_email && !email) setEmail(status.owner_email); // the email Cloudflare Access just checked
  }, [status.owner_email]); // eslint-disable-line react-hooks/exhaustive-deps
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const bad = checkNew(pw, pw2);
    if (bad) return setErr(bad);
    run(async () => next(await authApi.registerFirst(email, pw, status.setup_code ? setup : null), email.trim().toLowerCase()));
  };
  return (
    <form onSubmit={submit}>
      <h1>{t("创建你的账号")}</h1>
      <p className="auth-sub">
        {status.cloud
          ? t("这是 LACUNA 的第一个账号，也就是所有者：之后由你邀请别人。")
          : t("这是这台电脑上的第一个账号，以后打开 LACUNA 用它登录。")}
      </p>
      {status.setup_code && (
        <Field label={t("初始化码")} hint={t("在服务器的 auth/setup-code.txt 里")}>
          <span className="auth-input">
            <input value={setup} onChange={(e) => setSetup(e.target.value)} autoComplete="off" spellCheck={false} data-testid="auth-setup" required />
          </span>
        </Field>
      )}
      <EmailField email={email} setEmail={setEmail} autoFocus />
      <NewPassword pw={pw} setPw={setPw} pw2={pw2} setPw2={setPw2} />
      <Err err={err} />
      <button className="auth-btn" disabled={busy}>
        <BusyLabel busy={busy} label={t("创建账号")} busyLabel={t("创建中…")} />
      </button>
      {!status.cloud && (
        <p className="auth-note">
          <i />
          {t("密码只保存在这台电脑上（加密哈希），断网也能登录。")}
        </p>
      )}
    </form>
  );
}

/** Sign-up from an invite link: the email is fixed by the invite. */
function FromInvite({ token, go, next }: FormProps & { token: string }) {
  const [info, setInfo] = useState<{ email: string; by: string } | null>(null);
  const [gone, setGone] = useState<string | null>(null);
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const { busy, err, setErr, run } = useSubmit();
  useEffect(() => {
    authApi.invite(token).then((i) => {
      // a fresh browser opens the sign-up in the invite email's language
      if (!langChosen && i.lang && i.lang !== lang) setLang(i.lang);
      else setInfo(i);
    }, (e) => setGone(String(e.message ?? e)));
  }, [token]);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const bad = checkNew(pw, pw2);
    if (bad) return setErr(bad);
    run(async () => {
      const s = await authApi.registerInvite(token, pw);
      dropInvite();
      next(s, info!.email);
    });
  };
  if (gone)
    return (
      <div>
        <h1>{t("邀请链接用不了")}</h1>
        <p className="auth-sub" role="alert">
          {gone}
        </p>
        <button type="button" className="auth-btn" onClick={() => go("login")}>
          {t("去登录")}
        </button>
      </div>
    );
  return (
    <form onSubmit={submit}>
      <h1>{t("接受邀请")}</h1>
      <p className="auth-sub">{info ? t("{by} 邀请你加入 LACUNA。设一个密码就能开始。", { by: info.by }) : "…"}</p>
      <Field label={t("邮箱")}>
        <span className="auth-input">
          <input value={info?.email ?? ""} readOnly data-testid="auth-email" />
        </span>
      </Field>
      <NewPassword pw={pw} setPw={setPw} pw2={pw2} setPw2={setPw2} />
      <Err err={err} />
      <button className="auth-btn" disabled={busy || !info}>
        <BusyLabel busy={busy} label={t("创建账号")} busyLabel={t("创建中…")} />
      </button>
    </form>
  );
}

/** Password accepted: the code from the authenticator (or a recovery code). */
function Code({ ticket, who, go, next }: FormProps & { ticket: string; who: string }) {
  const [code, setCode] = useState("");
  const { busy, err, run } = useSubmit();
  const submit = (e: FormEvent) => {
    e.preventDefault();
    run(async () => next(await authApi.secondStep(ticket, code), who));
  };
  return (
    <form onSubmit={submit}>
      <h1>{t("两步验证")}</h1>
      <p className="auth-sub">{t("打开手机上的验证器 App，填 LACUNA 这一项现在显示的 6 位数字。")}</p>
      <SecondFactor value={code} onChange={setCode} wrong={err} />
      <Err err={err} />
      <button className="auth-btn" disabled={busy || code.length < 6}>
        <BusyLabel busy={busy} label={t("登录")} busyLabel={t("登录中…")} />
      </button>
      <p className="auth-foot">
        <button type="button" className="auth-link" onClick={() => go("login")}>
          ← {t("返回登录")}
        </button>
      </p>
    </form>
  );
}

/** Two-step sign-in is required and not set up yet: scan, confirm a code, then the recovery codes. */
function Enroll({ view, go, next }: FormProps & { view: Extract<View, { v: "enroll" }> }) {
  const [code, setCode] = useState("");
  const { busy, err, run } = useSubmit();
  const submit = (e: FormEvent) => {
    e.preventDefault();
    run(async () => next(await authApi.enroll(view.ticket, code), view.email));
  };
  return (
    <form onSubmit={submit}>
      <h1>{t("设置两步验证")}</h1>
      <p className="auth-sub">{t("LACUNA 在网上运行，每个账号都要开两步验证：登录时除了密码，还要手机上的 6 位数字。只需设置一次。")}</p>
      <TwoStepQR uri={view.uri} secret={view.secret} />
      <CodeInput value={code} onChange={setCode} label={t("两步验证码")} wrong={err} />
      <Err err={err} />
      <button className="auth-btn" disabled={busy || code.length < 6}>
        <BusyLabel busy={busy} label={t("确认并继续")} busyLabel={t("确认中…")} />
      </button>
      <p className="auth-foot">
        <button type="button" className="auth-link" onClick={() => go("login")}>
          ← {t("返回登录")}
        </button>
      </p>
    </form>
  );
}

function Forgot({ email, setEmail, go, next }: FormProps) {
  const [code, setCode] = useState("");
  const [pw, setPw] = useState("");
  const { busy, err, setErr, run } = useSubmit();
  const c = useCode();
  const step = c.sentTo ? 2 : 1;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (step === 1) return run(() => c.send(email));
    if (code.length !== 6) return setErr(t("填邮件里的 6 位验证码"));
    if (pw.length < MIN) return setErr(t("密码至少要 {n} 位", { n: MIN }));
    run(async () => next(await authApi.reset(email, code, pw), email.trim().toLowerCase()));
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
      <Err err={err} />
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

/** 申请试用: someone without an account asks for one; the site owner gets an email and sends the invite
 *  from 设置 → 成员与邀请 (lacuna_app/routes/auth_requests.py). */
function AskAccess({ status, email, setEmail, go }: FormProps) {
  const [show, setShow] = useState("");
  const [note, setNote] = useState("");
  const [human, setHuman] = useState<string | null>(null);
  const [tries, setTries] = useState(0);
  const [sent, setSent] = useState(false);
  const { busy, err, run } = useSubmit();
  const submit = (e: FormEvent) => {
    e.preventDefault();
    run(async () => {
      try {
        await authApi.requestAccess({ email, show, note, turnstile: human });
        setSent(true);
      } finally {
        if (status.turnstile) setTries((n) => n + 1);
      }
    });
  };
  if (sent)
    return (
      <div data-testid="auth-asked">
        <h1>{t("收到了")}</h1>
        <p className="auth-sub">{t("我们会尽快看你的申请。通过后，邀请邮件会发到 {email}，按邮件里的链接设个密码就能开始。", { email: email.trim() })}</p>
        <button type="button" className="auth-btn" onClick={() => go("login")}>
          {t("返回登录")}
        </button>
      </div>
    );
  return (
    <form onSubmit={submit}>
      <h1>{t("申请试用")}</h1>
      <p className="auth-sub">{t("LACUNA 目前仅限邀请。留下邮箱，通过后我们把邀请发给你：免费体验 1 小时音频，带一集示例。")}</p>
      <EmailField email={email} setEmail={setEmail} autoFocus />
      <Field label={t("节目名")} hint={t("可不填")}>
        <span className="auth-input">
          <input value={show} onChange={(e) => setShow(e.target.value)} maxLength={80} data-testid="auth-ask-show" />
        </span>
      </Field>
      <Field label={t("想用 LACUNA 做什么")} hint={t("可不填")}>
        <span className="auth-input">
          <textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} rows={3} data-testid="auth-ask-note" />
        </span>
      </Field>
      <Turnstile siteKey={status.turnstile} onToken={setHuman} nonce={tries} />
      <Err err={err} />
      <button className="auth-btn" disabled={busy || (!!status.turnstile && !human)}>
        <BusyLabel busy={busy} label={t("提交申请")} busyLabel={t("提交中…")} />
      </button>
      <p className="auth-foot">
        <button type="button" className="auth-link" onClick={() => go("login")}>
          ← {t("返回登录")}
        </button>
      </p>
    </form>
  );
}
