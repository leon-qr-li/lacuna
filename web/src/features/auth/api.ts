// API of the sign-in feature (lacuna_app/routes/auth.py)
import { req } from "../../api";

export type Role = "owner" | "admin" | "member";

export interface AuthStatus {
  accounts: boolean;
  /** no account yet: the app opens on "create the first account" */
  setup: boolean;
  email: string | null;
  role: Role | null;
  /** two-step sign-in is on for this account */
  twofa: boolean;
  /** the cloud server: two-step sign-in for everyone */
  require_2fa: boolean;
  cloud: boolean;
  /** the next account is the first (owner) */
  first: boolean;
  /** the first account also needs the setup code from the server */
  setup_code: boolean;
  /** owner only */
  mail: { configured: boolean; source: string | null; sender: string } | null;
}

/** What a sign-in step answers: signed in, or the two-step code comes next. */
export type Step =
  | { ok: true; step: "done"; recovery?: string[] }
  | { ok: true; step: "2fa"; ticket: string }
  | { ok: true; step: "enroll"; ticket: string; secret: string; uri: string };

export interface Device {
  id: string;
  created: number;
  seen: number;
  agent: string;
  current: boolean;
}

export interface Member {
  email: string;
  role: Role;
  created: number;
  twofa: boolean;
  disabled: boolean;
  seen: number | null;
}

export interface Invite {
  id: string;
  email: string;
  role: Role;
  by: string;
  created: number;
  exp: number;
}

export interface People {
  users: Member[];
  invites: Invite[];
}

/** Fired when any API call answers 401 (session expired / signed out elsewhere). */
export const AUTH_EVENT = "lacuna:auth";

export const authApi = {
  status: () => req<AuthStatus>("GET", "/api/auth/status"),
  login: (email: string, password: string, remember: boolean) =>
    req<Step>("POST", "/api/auth/login", { email, password, remember }),
  registerFirst: (email: string, password: string, setup_code: string | null) =>
    req<Step>("POST", "/api/auth/register", { email, password, setup_code, remember: true }),
  registerInvite: (invite: string, password: string) =>
    req<Step>("POST", "/api/auth/register", { invite, password, remember: true }),
  invite: (token: string) => req<{ email: string; role: Role; by: string; exp: number }>("POST", "/api/auth/invite", { token }),
  secondStep: (ticket: string, code: string) => req<Step>("POST", "/api/auth/2fa", { ticket, code }),
  enroll: (ticket: string, code: string) => req<Step>("POST", "/api/auth/2fa/enroll", { ticket, code }),
  sendCode: (email: string) => req<{ sent: true }>("POST", "/api/auth/code", { email, purpose: "reset" }),
  reset: (email: string, code: string, password: string) => req<Step>("POST", "/api/auth/reset", { email, code, password }),
  logout: () => req<{ ok: true }>("POST", "/api/auth/logout"),
  // my account
  password: (old: string, next: string) => req<{ ok: true }>("POST", "/api/auth/password", { old, new: next }),
  setup2fa: () => req<{ secret: string; uri: string }>("POST", "/api/auth/2fa/setup"),
  confirm2fa: (code: string) => req<AuthStatus & { recovery: string[] }>("POST", "/api/auth/2fa/confirm", { code }),
  newRecovery: (code: string) => req<{ recovery: string[] }>("POST", "/api/auth/2fa/recovery", { code }),
  off2fa: (code: string) => req<AuthStatus>("POST", "/api/auth/2fa/off", { code }),
  devices: () => req<{ sessions: Device[] }>("GET", "/api/auth/sessions"),
  endDevices: (id: string | null) => req<{ ended: number; sessions: Device[] }>("POST", "/api/auth/sessions/end", { id }),
  // members and invites (owner, admins)
  people: () => req<People>("GET", "/api/auth/users"),
  sendInvite: (email: string, role: Role) =>
    req<People & { link: string; mailed: boolean; mail_error: string | null; email: string }>("POST", "/api/auth/invites", { email, role }),
  revokeInvite: (id: string) => req<People>("DELETE", `/api/auth/invites/${encodeURIComponent(id)}`),
  updateMember: (email: string, c: { role?: Role; disabled?: boolean; reset_2fa?: boolean }) =>
    req<People>("POST", `/api/auth/users/${encodeURIComponent(email)}`, c),
  removeMember: (email: string) => req<People>("DELETE", `/api/auth/users/${encodeURIComponent(email)}`),
  // email (owner)
  config: (c: { sender?: string }) => req<AuthStatus>("POST", "/api/auth/config", c),
  saveResendKey: (key: string) => req<AuthStatus & { saved: true; where: string }>("POST", "/api/auth/resend-key", { key }),
  testMail: () => req<{ sent: true; to: string }>("POST", "/api/auth/test-mail"),
};
