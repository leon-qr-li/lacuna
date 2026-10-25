import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { AUTH_EVENT, authApi, type AuthStatus } from "./api";
import { AuthScreen, dropInvite, inviteToken } from "./AuthScreen";
import { PageLoading } from "../loading/Loading";
import { LegalPage, legalPath } from "../legal/Legal";
import { ConsentGate } from "../legal/Consent";
import { t } from "../../i18n";
import "./auth.css";

/** 用户条款 / 隐私政策 (/legal/terms, /legal/privacy) open for everyone, signed in or not; every other page is
 *  behind the sign-in. */
export function AuthGate({ children }: { children: ReactNode }) {
  const doc = legalPath();
  return doc ? <LegalPage doc={doc} /> : <Gate>{children}</Gate>;
}

/** Shows the sign-in screens until there is a session (or, before the first account exists, the
 *  "create your account" screen). Any 401 from the API brings the sign-in screen back. Signing in
 *  (or creating the account) always lands on 剧集, not on the page the sign-out happened on (设置).
 *  In the cloud, an account that hasn't agreed to the current 用户条款 / 隐私政策 agrees first. */
function Gate({ children }: { children: ReactNode }) {
  const [st, setSt] = useState<AuthStatus | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const signedOut = useRef(false);
  const check = useCallback(() => {
    authApi
      .status()
      .then((s) => {
        setSt(s);
        setErr(null);
      })
      .catch((e) => setErr(String(e.message ?? e)));
  }, []);
  useEffect(() => {
    check();
    window.addEventListener(AUTH_EVENT, check);
    return () => window.removeEventListener(AUTH_EVENT, check);
  }, [check]);
  if (!st) {
    if (err)
      return (
        <main className="auth-down">
          <p className="error">{t("连不上 LACUNA：{err}", { err })}</p>
          <button className="btn btn-outline" onClick={check}>
            {t("重试")}
          </button>
        </main>
      );
    return <PageLoading />;
  }
  if (st.setup || (st.accounts && !st.email)) {
    signedOut.current = true;
    return <AuthScreen status={st} onDone={check} />;
  }
  if (inviteToken()) return <InviteWhileSignedIn email={st.email} onDone={check} />;
  if (st.cloud && st.email && st.legal && st.legal.agreed !== st.legal.version)
    return (
      <ConsentGate
        version={st.legal.version}
        before={st.legal.agreed}
        onDone={check}
        onSignOut={() => {
          authApi.logout().finally(check);
        }}
      />
    );
  if (signedOut.current) {
    signedOut.current = false;
    if (!["", "#", "#/"].includes(window.location.hash)) window.history.replaceState(null, "", "#/");
  }
  return <>{children}</>;
}

/** An invite link opened in a browser that is signed in to another account: the invite is for a new
 *  account, so offer to sign out first instead of dropping it silently. */
function InviteWhileSignedIn({ email, onDone }: { email: string | null; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const signOut = () => {
    setBusy(true);
    authApi.logout().finally(onDone); // signed out, the gate opens the invite's sign-up page
  };
  const stay = () => {
    dropInvite();
    onDone();
  };
  return (
    <main className="auth-down" data-testid="invite-signed-in">
      <h1>{t("这是一个邀请链接")}</h1>
      <p>{t("它用来创建一个新账号，但这个浏览器已经登录了 {email}。要接受邀请，先退出当前账号。", { email: email ?? "" })}</p>
      <div className="row">
        <button className="btn btn-primary" onClick={signOut} disabled={busy}>
          {t("退出并接受邀请")}
        </button>
        <button className="btn btn-outline" onClick={stay} disabled={busy}>
          {t("继续用 {email}", { email: email ?? "" })}
        </button>
      </div>
    </main>
  );
}
