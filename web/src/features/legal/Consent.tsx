import { useState } from "react";
import { BusyLabel } from "../loading/Loading";
import { t } from "../../i18n";
import { AgreeBox, withLegalLinks } from "./Legal";
import { legalApi } from "./api";

/** Signed in, but the account agreed to an older version of the terms (or, made before they existed, to none):
 *  agree to the current one before the app opens, or sign out. */
export function ConsentGate({ version, before, onDone, onSignOut }: {
  version: string;
  /** the version agreed to before, if any */
  before: string | null;
  onDone: () => void;
  onSignOut: () => void;
}) {
  const [agree, setAgree] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const submit = async () => {
    if (!agree) return setErr(t("请先勾选同意用户条款和隐私政策"));
    setBusy(true);
    setErr(null);
    try {
      await legalApi.agree(version);
      onDone();
    } catch (e) {
      setErr(String((e as Error).message ?? e));
      setBusy(false);
    }
  };
  return (
    <main className="legal-consent" data-testid="legal-consent">
      <div className="legal-consent-card">
        <h1>{before ? t("用户条款和隐私政策更新了") : t("请确认用户条款和隐私政策")}</h1>
        <p className="muted">
          {withLegalLinks(
            before
              ? t("继续使用 LACUNA 之前，请看一下新版的 {terms} 和 {privacy}。")
              : t("LACUNA 现在有了正式的 {terms} 和 {privacy}。继续使用之前，请看一下并确认。"),
          )}
        </p>
        <ul className="legal-points">
          <li>{t("你的录音只存在我们自己的存储里，从不发给任何 AI 服务。")}</li>
          <li>{t("你的内容归你，我们不用它训练 AI，也不卖你的数据。")}</li>
          <li>{t("请只上传你有权使用的音乐和录音。")}</li>
        </ul>
        <AgreeBox checked={agree} onChange={setAgree} />
        {err && (
          <p className="error" role="alert">
            {err}
          </p>
        )}
        <div className="row">
          <button className="btn btn-primary" onClick={submit} disabled={busy} data-testid="legal-continue">
            <BusyLabel busy={busy} label={t("同意并继续")} busyLabel={t("保存中…")} />
          </button>
          <button className="btn btn-outline" onClick={onSignOut} disabled={busy}>
            {t("退出登录")}
          </button>
        </div>
        <p className="small muted">{t("版本 {v}", { v: version })}</p>
      </div>
    </main>
  );
}
