// API of this feature (its own file so features don't all edit src/api.ts)
import { req } from "../../api";

export interface AppInfo {
  /** the image's git commit; "dev" in a development checkout */
  version: string;
  platform: string;
  workspace: string;
  ffmpeg: string | null;
  ffprobe: string | null;
  models: boolean;
  busy: string[];
  /** the shared server (lacunastudio.app): new versions ship themselves, keys are the server's */
  cloud?: boolean;
  /** the staging site (preview.lacunastudio.app): a copy where new work is checked first */
  staging?: boolean;
  key: { present: boolean; source: string | null; editor: string; sdk: boolean };
}

export const settingsApi = {
  appInfo: () => req<AppInfo>("GET", "/api/app"),
  saveApiKey: (key: string) =>
    req<{ saved: boolean; where: string }>("POST", "/api/app/api-key", { key }),
};
