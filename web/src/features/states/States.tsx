import type { ReactNode } from "react";
import type { RequestError } from "../../api";
import { t } from "../../i18n";

/**
 * What a person reads when something failed to load (batch 7, B2 / B3): never the raw
 * "Error: Internal Server Error" or "TypeError: Failed to fetch". A 4xx keeps the server's own
 * (translated) reason; a 5xx or a dropped connection gets a plain sentence.
 */
export function friendlyError(e: unknown): string {
  // a caller that kept only the server's message (a string): that is the reason, not a lost connection
  if (typeof e === "string")
    return /fetch|network|load failed/i.test(e) || !e ? friendlyError(undefined) : friendlyError(Object.assign(new Error(e), { status: 400 }));
  const err = e as RequestError | undefined;
  const status = err?.status;
  const msg = String(err?.message ?? "");
  if (status === undefined || /fetch|network|load failed/i.test(msg)) return t("连不上 LACUNA，检查一下网络再试。");
  if (status >= 500 || !msg || /^(internal server error|bad gateway|service unavailable|gateway timeout|not found|bad request)$/i.test(msg))
    return t("这一页暂时没加载出来，请稍后再试。");
  return msg;
}

/** A failed page or panel: what went wrong, plus retry and (optionally) a way back. */
export function ErrorState(props: { title?: string; error: unknown; onRetry?: () => void; back?: { href: string; label: string }; compact?: boolean }) {
  return (
    <div className={`state-box state-error${props.compact ? " state-compact" : ""}`} role="alert" data-testid="error-state">
      <span className="state-icon" aria-hidden="true">
        !
      </span>
      {props.title && <h2 className="state-title">{props.title}</h2>}
      <p className="state-text">{friendlyError(props.error)}</p>
      {(props.onRetry || props.back) && (
        <div className="state-actions">
          {props.onRetry && (
            <button type="button" className="btn btn-primary btn-small" onClick={props.onRetry} data-testid="error-retry">
              {t("重试")}
            </button>
          )}
          {props.back && (
            <a className="btn btn-outline btn-small linkbtn" href={props.back.href}>
              {props.back.label}
            </a>
          )}
        </div>
      )}
    </div>
  );
}

/** A page or list with nothing in it yet: an icon, one sentence, and the one thing to do next (T4). */
export function EmptyState(props: { icon?: ReactNode; title: string; text?: string; action?: ReactNode; testid?: string }) {
  return (
    <div className="state-box state-empty" data-testid={props.testid ?? "empty-state"}>
      <span className="state-icon" aria-hidden="true">
        {props.icon ?? "◌"}
      </span>
      <h2 className="state-title">{props.title}</h2>
      {props.text && <p className="state-text">{props.text}</p>}
      {props.action && <div className="state-actions">{props.action}</div>}
    </div>
  );
}
