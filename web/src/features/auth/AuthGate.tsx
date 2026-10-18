import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { AUTH_EVENT, authApi, type AuthStatus } from "./api";
import { AuthScreen } from "./AuthScreen";
import { PageLoading } from "../loading/Loading";
import { t } from "../../i18n";
import "./auth.css";

/** Shows the sign-in screens until there is a session (or, before the first account exists, the
 *  "create your account" screen). Any 401 from the API brings the sign-in screen back. Signing in
 *  (or creating the account) always lands on 剧集, not on the page the sign-out happened on (设置). */
export function AuthGate({ children }: { children: ReactNode }) {
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
  if (signedOut.current) {
    signedOut.current = false;
    if (!["", "#", "#/"].includes(window.location.hash)) window.history.replaceState(null, "", "#/");
  }
  return <>{children}</>;
}
