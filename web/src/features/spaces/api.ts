// API of workspaces (lacuna_app/routes/spaces.py)
import { req } from "../../api";
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
}

/** 邀请协作: a project's collaborators and the invites waiting for them */
export interface ProjectPeople {
  id: string;
  name: string;
  members: { email: string; role: SpaceRole }[];
  invites: { id: string; email: string; role: SpaceRole; exp: number }[];
  /** only LACUNA admins may invite someone without an account */
  can_invite_new: boolean;
  joined?: string;
  invited?: string;
  link?: string;
  mailed?: boolean;
  mail_error?: string | null;
}

export interface SpaceInfo {
  id: string;
  name: string;
  created: number;
  members: { email: string; role: SpaceRole }[];
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
  withdraw: (id: string, invite: string) =>
    req<ProjectPeople>("DELETE", `/api/spaces/${encodeURIComponent(id)}/invites/${encodeURIComponent(invite)}`),
};
