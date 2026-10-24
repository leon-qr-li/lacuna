// The admin's API (lacuna_app/admin_api.py). Every change carries the X-Lacuna-Admin header (the server refuses
// changes without it, so another website can't make the browser send one). A dangerous action answered with
// 403 "stepup" asks for the authenticator code (stepUp, set by the shell) and is tried again once.
import { t } from "./i18n";

export type AdminError = Error & { status?: number; code?: string };

let askCode: (() => Promise<boolean>) | null = null;
/** The shell's 再输一次验证码 dialog: resolves true once a code was accepted. */
export function onStepUp(f: () => Promise<boolean>) {
  askCode = f;
}
let signedOut: (() => void) | null = null;
export function onSignedOut(f: () => void) {
  signedOut = f;
}

async function call<T>(method: string, url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method,
    credentials: "same-origin",
    headers: { ...(method === "GET" ? {} : { "X-Lacuna-Admin": "1" }), ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.ok) return (res.headers.get("content-type") || "").includes("json") ? ((await res.json()) as T) : (undefined as T);
  let detail: unknown = res.statusText;
  try {
    detail = (await res.json()).detail ?? detail;
  } catch {
    /* not JSON */
  }
  const code = typeof detail === "object" && detail ? (detail as { code?: string }).code : undefined;
  const msg = typeof detail === "object" && detail ? (detail as { message?: string }).message ?? t("出错了") : String(detail);
  const err: AdminError = new Error(msg);
  err.status = res.status;
  err.code = code;
  throw err;
}

export async function api<T>(method: string, url: string, body?: unknown): Promise<T> {
  try {
    return await call<T>(method, url, body);
  } catch (e) {
    const err = e as AdminError;
    if (err.status === 403 && err.code === "stepup" && askCode && (await askCode())) return call<T>(method, url, body);
    if (err.status === 401 && !url.startsWith("/api/admin/auth/") && signedOut) signedOut();
    throw err;
  }
}

export const get = <T,>(url: string) => api<T>("GET", url);
