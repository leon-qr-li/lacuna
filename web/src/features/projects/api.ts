import { useEffect, useState } from "react";
import { spacesApi, type Spaces } from "../spaces/api";

// Projects are the server's workspaces (lacuna_app/spaces.py, decision projects-albums): one fetch shared by
// the top-bar menu, the project list and the settings page; a change anywhere updates them all.
let cache: Spaces | null | undefined;
let pending: Promise<Spaces | null> | null = null;
const subs = new Set<(s: Spaces | null) => void>();

export function setProjects(s: Spaces | null) {
  cache = s;
  subs.forEach((f) => f(s));
}

export function loadProjects(fresh = false): Promise<Spaces | null> {
  if (!fresh && cache !== undefined) return Promise.resolve(cache);
  if (!fresh && pending) return pending;
  pending = spacesApi
    .list()
    .catch(() => null)
    .then((s) => {
      pending = null;
      setProjects(s);
      return s;
    });
  return pending;
}

/** The signed-in person's projects; undefined while loading, null without accounts (nothing to show). */
export function useProjects(): Spaces | null | undefined {
  const [s, set] = useState<Spaces | null | undefined>(cache);
  useEffect(() => {
    subs.add(set);
    void loadProjects();
    return () => {
      subs.delete(set);
    };
  }, []);
  return s;
}

/** Everything on screen belongs to the project you were in: open the new one's 剧集 fresh. */
export async function openProject(id: string) {
  await spacesApi.switchTo(id);
  window.location.hash = "#/";
  window.location.reload();
}

/** Where you go after making a project: its 剧集, which asks for its hosts first. */
export function enterNew() {
  window.location.hash = "#/";
  window.location.reload();
}
