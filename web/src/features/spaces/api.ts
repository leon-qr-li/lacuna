// API of workspaces (lacuna_app/routes/spaces.py)
import { req } from "../../api";

export type SpaceRole = "admin" | "editor" | "viewer";

export interface MySpace {
  id: string;
  name: string;
  role: SpaceRole;
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
  create: (name: string) => req<Spaces>("POST", "/api/spaces", { name }),
  rename: (id: string, name: string) => req<Spaces>("POST", `/api/spaces/${encodeURIComponent(id)}`, { name }),
  member: (id: string, email: string, role: SpaceRole | null) =>
    req<Spaces>("POST", `/api/spaces/${encodeURIComponent(id)}/members`, { email, role }),
};
