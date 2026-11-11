// API of workspaces (lacuna_app/routes/spaces.py)
import { failure, req } from "../../api";
import { lang as uiLang, type Lang } from "../../i18n";

export type SpaceRole = "admin" | "editor" | "viewer";

export interface MySpace {
  id: string;
  /** the project's name (its show name once set) */
  name: string;
  role: SpaceRole;
  /** who brought you in (null: you made it, or it was set up for you) */
  by?: string | null;
  episodes?: number;
  albums?: number;
  people?: number;
  /** last change, seconds since 1970 */
  updated?: number;
  /** its solid colour while it has no picture */
  color?: string;
  /** its square picture's address, null: none (the colour shows) */
  picture?: string | null;
  /** in 已归档: read-only for everyone until restored */
  archived?: boolean;
  /** you may delete it for good (its creator, or LACUNA's owner) */
  can_delete?: boolean;
  /** you are LACUNA support looking in read-only (the show allowed it, decision 2026-10-21-roles) */
  support?: boolean;
  /** LACUNA 示例节目: your own practice show, not counted against the plan (lacuna_app/sample.py) */
  sample?: boolean;
}

/** 邀请协作: a project's collaborators and the invites waiting for them */
export interface ProjectPeople {
  id: string;
  name: string;
  members: { email: string; role: SpaceRole; name?: string | null }[];
  invites: { id: string; email: string; role: SpaceRole; exp: number }[];
  /** this person may send a sign-up link to someone without an account (site admins; show admins once
   *  「新成员需站长批准」 is off) */
  can_invite_new: boolean;
  /** 新成员需站长批准 is on: someone without an account becomes a 搭档申请 for the site owner */
  needs_approval?: boolean;
  /** 搭档申请 for this show still waiting for the site owner */
  requests?: { id: string; email: string; role: SpaceRole; created: number }[];
  /** 「允许 LACUNA 支持查看」 is on until then (seconds since 1970), null: off */
  support_until: number | null;
  /** the plan of the account that made the show (its limits apply here) */
  plan: "trial" | "basic" | "pro";
  /** people in it besides the person who made it */
  collaborators: number;
  joined?: string;
  invited?: string;
  /** a 搭档申请 went to the site owner */
  requested?: string;
  /** the site already invited them: they join this show when they sign up */
  joins_later?: string;
  link?: string;
  mailed?: boolean;
  mail_error?: string | null;
}

export interface SpaceInfo {
  id: string;
  name: string;
  created: number;
  members: { email: string; role: SpaceRole; name?: string | null }[];
}

export interface Spaces {
  current: MySpace | null;
  mine: MySpace[];
  /** workspaces this person manages (every one for the site owner and admins) */
  all?: SpaceInfo[];
}

export const spacesApi = {
  /** null when nobody is signed in (the desktop app without accounts): no workspaces to show */
  list: async (): Promise<Spaces | null> => {
    const r = await fetch("/api/spaces");
    return r.ok ? ((await r.json()) as Spaces) : null;
  },
  switchTo: (id: string) => req<Spaces>("POST", "/api/spaces/switch", { id }),
  /** a new project of your own; you are moved into it */
  create: (name: string) => req<Spaces & { created: string }>("POST", "/api/spaces", { name }),
  rename: (id: string, name: string) => req<Spaces>("POST", `/api/spaces/${encodeURIComponent(id)}`, { name }),
  member: (id: string, email: string, role: SpaceRole | null) =>
    req<Spaces>("POST", `/api/spaces/${encodeURIComponent(id)}/members`, { email, role }),
  people: (id: string) => req<ProjectPeople>("GET", `/api/spaces/${encodeURIComponent(id)}/people`),
  invite: (id: string, email: string, role: SpaceRole, lang: Lang = uiLang) =>
    req<ProjectPeople>("POST", `/api/spaces/${encodeURIComponent(id)}/invite`, { email, role, lang }),
  /** any image; the server cuts it to a centred square */
  setPicture: async (id: string, file: Blob): Promise<Spaces> => {
    const url = `/api/spaces/${encodeURIComponent(id)}/picture`;
    const r = await fetch(url, { method: "POST", headers: { "Content-Type": file.type || "application/octet-stream" }, body: file });
    if (!r.ok) throw await failure(r, url);
    return (await r.json()) as Spaces;
  },
  dropPicture: (id: string) => req<Spaces>("DELETE", `/api/spaces/${encodeURIComponent(id)}/picture`),
  /** archive (read-only, under 已归档) or restore */
  archive: (id: string, archived: boolean) => req<Spaces>("POST", `/api/spaces/${encodeURIComponent(id)}/archive`, { archived }),
  /** for good, from 已归档, with the project's name typed */
  remove: (id: string, confirm: string) =>
    req<Spaces & { deleted: string }>("DELETE", `/api/spaces/${encodeURIComponent(id)}`, { confirm }),
  /** 「允许 LACUNA 支持查看」 for 7 days, or off */
  support: (id: string, on: boolean) => req<ProjectPeople>("POST", `/api/spaces/${encodeURIComponent(id)}/support`, { on }),
  withdraw: (id: string, invite: string) =>
    req<ProjectPeople>("DELETE", `/api/spaces/${encodeURIComponent(id)}/invites/${encodeURIComponent(invite)}`),
};
