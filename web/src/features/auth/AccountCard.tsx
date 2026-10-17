import { useCallback, useEffect, useState } from "react";
import { AUTH_EVENT, authApi, type AuthStatus } from "./api";
import { BusyLabel } from "../loading/Loading";
import { t } from "../../i18n";
import "./auth.css";

const KEY_SOURCE: Record<string, string> = {
  env: t("环境变量"),
  "registry-user": t("Windows 用户环境变量"),
  keychain: t("macOS 钥匙串"),
  file: t("本机文件"),
  test: t("测试"),
};

/** 设置 → 账号与邮件: who is signed in, sign out, Resend key + sender, test email, open sign-up. */
export function AccountCard() {
  const [st, setSt] = useState<AuthStatus | null>(null);
  const [key, setKey] = useState("");
  const [sender, setSender] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const load = useCallback(() => {
    authApi
      .status()
      .then((s) => {
        setSt(s);
        setSender(s.mail.sender);
      })
      .catch(() => setSt(null));
  }, []);
  useEffect(load, [load]);
  if (!st || !st.email) return null;

  const act = async (name: string, fn: () => Promise<string | void>) => {
    setBusy(name);
    setMsg(null);
    try {
      const text = await fn();
      if (text) setMsg({ ok: true, text });
    } catch (e) {
      setMsg({ ok: false, text: String((e as Error).message ?? e) });
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="card account-card" aria-label={t("账号与邮件")}>
      <div className="card-head">
        <h2>{t("账号与邮件")}</h2>
        <button
          className="btn btn-outline btn-small"
          disabled={!!busy}
          onClick={() =>
            act("logout", async () => {
              await authApi.logout();
              window.dispatchEvent(new Event(AUTH_EVENT));
            })
          }
        >
          {t("退出登录")}
        </button>
      </div>
      <p className="muted small" data-testid="account-email">
        {t("已登录：{email}", { email: st.email })}
      </p>

      <div className="set-row">
        <div>
          <strong>Resend API key</strong>
          <p className="muted small">
            {t("注册验证码和「忘记密码」的邮件用 Resend 发。只保存在这台电脑上，不会显示出来。")}
          </p>
        </div>
        <span className={st.mail.configured ? "badge badge-confirmed" : "badge badge-unknown"} data-testid="resend-state">
          {st.mail.configured
            ? t("已接上（{p0}）", { p0: KEY_SOURCE[st.mail.source ?? ""] ?? st.mail.source })
            : t("还没接上")}
        </span>
      </div>
      <div className="row gap">
        <input
          className="grow"
          type="password"
          autoComplete="off"
          placeholder="re_…"
          aria-label="Resend API key"
          value={key}
          onChange={(e) => setKey(e.target.value)}
        />
        <button
          className="btn btn-outline"
          disabled={!!busy || key.trim().length < 20}
          onClick={() =>
            act("key", async () => {
              const r = await authApi.saveResendKey(key);
              setSt(r);
              setKey("");
              return t("已保存。");
            })
          }
        >
          <BusyLabel busy={busy === "key"} label={st.mail.configured ? t("换一个") : t("保存")} />
        </button>
      </div>

      <div className="set-row">
        <div>
          <strong>{t("发件地址")}</strong>
          <p className="muted small">
            {t("没验证域名时用 onboarding@resend.dev，只能发到你注册 Resend 的邮箱。验证了域名就改成那个域名下的地址。")}
          </p>
        </div>
      </div>
      <div className="row gap">
        <input className="grow" value={sender} aria-label={t("发件地址")} onChange={(e) => setSender(e.target.value)} />
        <button
          className="btn btn-outline"
          disabled={!!busy || sender.trim() === st.mail.sender}
          onClick={() => act("sender", async () => setSt(await authApi.config({ sender })))}
        >
          {t("保存")}
        </button>
        <button
          className="btn btn-outline"
          disabled={!!busy || !st.mail.configured}
          onClick={() => act("test", async () => t("测试邮件已发到 {to}，去收件箱看看。", { to: (await authApi.testMail()).to }))}
        >
          <BusyLabel busy={busy === "test"} label={t("发测试邮件")} busyLabel={t("发送中…")} />
        </button>
      </div>

      <div className="set-row">
        <div>
          <strong>{t("允许新注册")}</strong>
          <p className="muted small">{t("关着时登录页不显示「注册」。要给别人（比如 Pei）开账号时再打开，开完记得关上。")}</p>
        </div>
        <label className="switch">
          <input
            type="checkbox"
            checked={st.allow_register}
            data-testid="allow-register"
            disabled={!!busy}
            onChange={(e) => act("reg", async () => setSt(await authApi.config({ allow_register: e.target.checked })))}
          />
          <span />
        </label>
      </div>
      {msg && (
        <p className={msg.ok ? "account-ok small" : "error small"} role="status">
          {msg.text}
        </p>
      )}
    </section>
  );
}
