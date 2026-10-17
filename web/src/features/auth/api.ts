// API of the sign-in feature (lacuna_app/routes/auth.py)
import { req } from "../../api";

export interface AuthStatus {
  accounts: boolean;
  /** no account yet: the app opens on "create the first account" */
  setup: boolean;
  email: string | null;
  allow_register: boolean;
  /** the next account is the first (owner): no email code needed */
  first: boolean;
  mail: { configured: boolean; source: string | null; sender: string };
}

/** Fired when any API call answers 401 (session expired / signed out elsewhere). */
export const AUTH_EVENT = "lacuna:auth";

export const authApi = {
  status: () => req<AuthStatus>("GET", "/api/auth/status"),
  login: (email: string, password: string, remember: boolean) =>
    req<{ ok: true }>("POST", "/api/auth/login", { email, password, remember }),
  register: (email: string, password: string, code: string | null, remember: boolean) =>
    req<{ ok: true }>("POST", "/api/auth/register", { email, password, code, remember }),
  sendCode: (email: string, purpose: "register" | "reset") => req<{ sent: true }>("POST", "/api/auth/code", { email, purpose }),
  reset: (email: string, code: string, password: string) => req<{ ok: true }>("POST", "/api/auth/reset", { email, code, password }),
  logout: () => req<{ ok: true }>("POST", "/api/auth/logout"),
  config: (c: { allow_register?: boolean; sender?: string }) => req<AuthStatus>("POST", "/api/auth/config", c),
  saveResendKey: (key: string) => req<AuthStatus & { saved: true; where: string }>("POST", "/api/auth/resend-key", { key }),
  testMail: () => req<{ sent: true; to: string }>("POST", "/api/auth/test-mail"),
};
