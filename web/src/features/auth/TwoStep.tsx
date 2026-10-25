import { useEffect, useMemo, useRef, useState } from "react";
import qrcode from "qrcode-generator";
import { t } from "../../i18n";

/** The authenticator-app QR code (dark on a white tile in both themes, so every phone can scan it)
 *  with the key written out for typing it in by hand. */
export function TwoStepQR({ uri, secret }: { uri: string; secret: string }) {
  const src = useMemo(() => {
    const qr = qrcode(0, "M");
    qr.addData(uri);
    qr.make();
    return qr.createDataURL(5, 2);
  }, [uri]);
  const [show, setShow] = useState(false);
  return (
    <div className="twostep-qr">
      <img src={src} alt={t("两步验证二维码")} width={180} height={180} data-testid="twostep-qr" />
      <div>
        <ol className="twostep-how">
          <li>{t("在手机上打开验证器 App（Google Authenticator、Microsoft Authenticator、1Password、iPhone 的「密码」都行）。")}</li>
          <li>{t("点「添加」，扫左边的二维码。")}</li>
          <li>{t("把 App 里 LACUNA 这一项的 6 位数字填到下面。")}</li>
        </ol>
        <button type="button" className="auth-link" onClick={() => setShow(!show)}>
          {show ? t("收起密钥") : t("扫不了？手动输入密钥")}
        </button>
        {show && (
          <code className="twostep-secret" data-testid="twostep-secret">
            {secret.replace(/(.{4})/g, "$1 ").trim()}
          </code>
        )}
      </div>
    </div>
  );
}

/** Six boxes over one real input (paste and autofill work as usual). A click on a box selects that digit,
 *  so typing replaces it; `wrong` (the last failed try) empties the boxes and puts the cursor back in the first. */
export function CodeInput({ value, onChange, label, wrong }: { value: string; onChange: (s: string) => void; label?: string; wrong?: unknown }) {
  const ref = useRef<HTMLInputElement>(null);
  const [at, setAt] = useState<number | null>(null); // the selected box, null: the next empty one
  useEffect(() => {
    if (!wrong) return;
    onChange("");
    setAt(null);
    ref.current?.focus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wrong]);
  const pick = (clientX: number) => {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const i = Math.max(0, Math.min(5, Math.floor(((clientX - r.left) / r.width) * 6)));
    if (i < value.length) {
      el.setSelectionRange(i, i + 1);
      setAt(i);
    } else {
      el.setSelectionRange(value.length, value.length);
      setAt(null);
    }
  };
  const cur = at ?? Math.min(value.length, 5);
  return (
    <div className="auth-code">
      <input
        ref={ref}
        inputMode="numeric"
        autoComplete="one-time-code"
        maxLength={6}
        value={value}
        aria-label={label ?? t("验证码")}
        data-testid="auth-code"
        onPointerUp={(e) => pick(e.clientX)}
        onKeyDown={(e) => {
          if (at !== null && /^\d$/.test(e.key)) {
            // typing over the selected digit: replace it, then move to the next box
            e.preventDefault();
            const next = value.slice(0, at) + e.key + value.slice(at + 1);
            onChange(next);
            const n = at + 1;
            requestAnimationFrame(() => {
              if (n < next.length) {
                ref.current?.setSelectionRange(n, n + 1);
                setAt(n);
              } else {
                ref.current?.setSelectionRange(next.length, next.length);
                setAt(null);
              }
            });
          } else if (e.key === "ArrowLeft" || e.key === "ArrowRight" || e.key === "Backspace" || e.key === "Delete") {
            setAt(null);
          }
        }}
        onChange={(e) => {
          setAt(null);
          onChange(e.target.value.replace(/\D/g, "").slice(0, 6));
        }}
      />
      {Array.from({ length: 6 }, (_, i) => (
        <span key={i} className={i === cur ? "is-cur" : ""} data-testid="auth-code-box">
          {value[i] ?? ""}
        </span>
      ))}
    </div>
  );
}

/** A two-step code from the app, or (after a click) one of the recovery codes. */
export function SecondFactor({ value, onChange, wrong }: { value: string; onChange: (s: string) => void; wrong?: unknown }) {
  const [recovery, setRecovery] = useState(false);
  return (
    <>
      {recovery ? (
        <label className="auth-field">
          <span className="auth-label">{t("恢复码")}</span>
          <span className="auth-input">
            <input
              value={value}
              autoComplete="off"
              spellCheck={false}
              placeholder="abcde-23456"
              data-testid="auth-recovery"
              onChange={(e) => onChange(e.target.value.slice(0, 16))}
            />
          </span>
        </label>
      ) : (
        <CodeInput value={value} onChange={onChange} label={t("两步验证码")} wrong={wrong} />
      )}
      <div className="auth-hint">
        <span>{recovery ? t("每个恢复码只能用一次。") : t("手机上验证器 App 里 LACUNA 这一项的 6 位数字。")}</span>
        <button
          type="button"
          className="auth-link"
          onClick={() => {
            setRecovery(!recovery);
            onChange("");
          }}
        >
          {recovery ? t("用手机上的数字") : t("手机不在身边？用恢复码")}
        </button>
      </div>
    </>
  );
}

/** The ten one-time recovery codes, shown once: copy or download, then confirm they are saved. */
export function RecoveryCodes({ codes, email, onDone, doneLabel }: {
  codes: string[];
  email: string;
  onDone: () => void;
  doneLabel: string;
}) {
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState(false);
  const text = `LACUNA ${t("恢复码")} · ${email}\n\n${codes.join("\n")}\n`;
  const file = useMemo(() => URL.createObjectURL(new Blob([text], { type: "text/plain" })), [text]);
  return (
    <div className="twostep-recovery">
      <ul className="twostep-codes" data-testid="recovery-codes">
        {codes.map((c) => (
          <li key={c}>{c}</li>
        ))}
      </ul>
      <div className="row gap8">
        <button
          type="button"
          className="btn btn-outline btn-small"
          onClick={() => navigator.clipboard?.writeText(text).then(() => setCopied(true), () => setCopied(false))}
        >
          {copied ? t("已复制") : t("复制")}
        </button>
        <a className="btn btn-outline btn-small" href={file} download="LACUNA-recovery-codes.txt">
          {t("下载 .txt")}
        </a>
      </div>
      <label className="auth-check twostep-saved">
        <input type="checkbox" checked={saved} onChange={(e) => setSaved(e.target.checked)} data-testid="recovery-saved" />
        {t("我已经把恢复码存好了（比如密码管理器里）")}
      </label>
      <button type="button" className="auth-btn" disabled={!saved} onClick={onDone}>
        {doneLabel}
      </button>
    </div>
  );
}
