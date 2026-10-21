import { useEffect, useRef } from "react";
import { lang } from "../../i18n";

// Cloudflare's widget script, loaded once and only on a server that has Turnstile on
const SRC = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";

interface TurnstileApi {
  render: (el: HTMLElement, o: Record<string, unknown>) => string;
  reset: (id: string) => void;
  remove: (id: string) => void;
}
declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

let loading: Promise<TurnstileApi> | null = null;
function load(): Promise<TurnstileApi> {
  if (window.turnstile) return Promise.resolve(window.turnstile);
  loading ??= new Promise((ok, fail) => {
    const s = document.createElement("script");
    s.src = SRC;
    s.async = true;
    s.onload = () => (window.turnstile ? ok(window.turnstile) : fail(new Error("turnstile")));
    s.onerror = () => {
      loading = null;
      fail(new Error("turnstile"));
    };
    document.head.appendChild(s);
  });
  return loading;
}

/** The human check on the sign-in and 申请试用 forms (lacuna_app/turnstile.py). `siteKey` null: off, renders
 *  nothing. `onToken` gets Cloudflare's one-time token (null when it expires); `nonce` changing asks for a
 *  fresh token (a token works once, so after a failed attempt). */
export function Turnstile({ siteKey, onToken, nonce = 0 }: { siteKey: string | null | undefined; onToken: (t: string | null) => void; nonce?: number }) {
  const box = useRef<HTMLDivElement>(null);
  const id = useRef<string | null>(null);
  useEffect(() => {
    if (!siteKey || !box.current) return;
    let gone = false;
    load().then((ts) => {
      if (gone || !box.current) return;
      const dark = document.documentElement.dataset.theme === "dark";
      id.current = ts.render(box.current, {
        sitekey: siteKey,
        theme: dark ? "dark" : "light",
        language: lang === "en" ? "en" : "zh-cn",
        size: "flexible",
        callback: (tok: string) => onToken(tok),
        "expired-callback": () => onToken(null),
        "error-callback": () => onToken(null),
      });
    }, () => onToken(null));
    return () => {
      gone = true;
      if (id.current && window.turnstile) window.turnstile.remove(id.current);
      id.current = null;
    };
  }, [siteKey]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (nonce && id.current && window.turnstile) {
      onToken(null);
      window.turnstile.reset(id.current);
    }
  }, [nonce]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!siteKey) return null;
  return <div className="auth-turnstile" ref={box} data-testid="auth-turnstile" />;
}
