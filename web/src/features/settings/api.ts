// API of this feature (its own file so features don't all edit src/api.ts)
import { req } from "../../api";

export interface AppInfo {
  version: string;
  installed: boolean;
  platform: string;
  workspace: string;
  home: string | null;
  ffmpeg: string | null;
  ffprobe: string | null;
  models: boolean;
  busy: string[];
  /** the shared server (lacunastudio.app): updates ship themselves, keys are the server's */
  cloud?: boolean;
  key: { present: boolean; source: string | null; editor: string; sdk: boolean };
  update: {
    installed: boolean;
    version: string;
    latest: string | null;
    available: boolean;
    notes: string;
    published: string | null;
    error: string | null;
    job: { state: "running" | "ready" | "error"; version: string; progress: number; error: string | null } | null;
    last_update: { at: string; ok: boolean; message: string; from?: string | null; to?: string } | null;
  };
}

export const settingsApi = {
  appInfo: () => req<AppInfo>("GET", "/api/app"),
  checkUpdate: () => req<AppInfo>("POST", "/api/app/update/check"),
  prepareUpdate: () => req<AppInfo>("POST", "/api/app/update/prepare"),
  applyUpdate: () => req<{ restarting: boolean; version: string }>("POST", "/api/app/update/apply"),
  saveApiKey: (key: string) =>
    req<{ saved: boolean; where: string; restarting: boolean }>("POST", "/api/app/api-key", { key }),
};
