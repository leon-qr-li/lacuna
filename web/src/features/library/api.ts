// API of this feature (moved out of src/api.ts so features don't all edit one file)
import type { Usage } from "../../api";
import { ep, req } from "../../api";

export type CreditStatus = "confirmed" | "suggested" | "unknown";

export interface Credit {
  title: string | null;
  artist: string | null;
  composer: string | null;
  album: string | null;
  film: string | null;
  year: number | null;
  status: CreditStatus;
  source: string | null;
  sources: string[];
  note?: string;
}

export type Kind = "intro" | "outro" | "interlude" | "bed" | "dialogue" | "trailer" | "other";

export interface Asset {
  id: string;
  kind: Kind;
  kind_label: string;
  file: string;
  name: string;
  duration_s: number;
  lufs: number | null;
  note: string;
  tags: Record<string, string>;
  credit: Credit;
  credit_line: string;
  added_at: string;
}

export interface LibraryView {
  assets: Asset[];
  series: { name: string; default: boolean }[];
  folder: string;
  kinds: Record<Kind, string>; // Leon's fixed list of uses, in display order
  kind_roles: Record<Kind, Role>; // where the music page puts an asset of that use
  lookup: boolean; // Claude credit lookup available (API key found)
}

export type Role = "intro" | "interlude" | "outro" | "bed" | "clip";

export interface Placement {
  id: string;
  asset_id: string;
  role: Role;
  role_label: string;
  status: "applied" | "proposed";
  src_in_s: number;
  src_out_s: number;
  overlap_s: number;
  gain_db: number;
  lead_s?: number;
  asset_name: string | null;
  asset_duration_s?: number;
  credit_line: string;
  credit_status?: CreditStatus;
  start_s: number | null;
  end_s: number | null;
  voice_at_s?: number | null;
  inserted_s?: number;
  missing: boolean;
}

export interface BgmCredit {
  role: Role;
  role_label: string;
  start_s: number;
  end_s: number;
  credit_line: string;
  credit_status: CreditStatus;
}

export interface MusicView {
  placements: Placement[];
  voice_duration: number;
  duration: number;
  mix_version: string;
  mix_url: string;
  credits: BgmCredit[];
  series: string | null;
  series_suggestion: { name: string } | null;
  roles: Record<Role, string>;
}

export type PlacementPatch = Partial<{
  asset_id: string;
  role: Role;
  at_s: number;
  until_s: number;
  src_in_s: number;
  src_out_s: number;
  overlap_s: number;
  gain_db: number;
  lead_s: number;
}>;

async function uploadAsset(file: File, kind: string, note = ""): Promise<{ asset: Asset; duplicate: boolean }> {
  const q = new URLSearchParams({ name: file.name, kind, note });
  const res = await fetch(`/api/library/upload?${q}`, {
    method: "POST",
    headers: { "Content-Type": "application/octet-stream" },
    body: file,
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      msg = (await res.json()).detail ?? msg;
    } catch {
      /* not JSON */
    }
    throw new Error(String(msg));
  }
  return res.json() as Promise<{ asset: Asset; duplicate: boolean }>;
}

export const libraryApi = {
  library: () => req<LibraryView>("GET", "/api/library"),
  uploadAsset,
  scanLibrary: () => req<LibraryView & { added: Asset[] }>("POST", "/api/library/scan"),
  openLibrary: () => req<{ folder: string }>("POST", "/api/library/open"),
  updateAsset: (aid: string, body: { note?: string; kind?: string; credit?: Partial<Credit>; confirm?: boolean }) =>
    req<{ asset: Asset }>("PATCH", `/api/library/assets/${aid}`, body),
  lookupCredit: (aid: string) =>
    req<{ asset: Asset; message: string; usage: Usage | null }>("POST", `/api/library/assets/${aid}/lookup`),
  removeAsset: (aid: string) => req<{ ok: boolean }>("DELETE", `/api/library/assets/${aid}`),
  music: (id: string) => req<MusicView>("GET", `${ep(id)}/music`),
  addPlacement: (id: string, body: PlacementPatch & { asset_id: string; role: Role }) =>
    req<MusicView>("POST", `${ep(id)}/music`, body),
  updatePlacement: (id: string, pid: string, body: PlacementPatch) =>
    req<MusicView>("PATCH", `${ep(id)}/music/${pid}`, body),
  removePlacement: (id: string, pid: string) => req<MusicView>("DELETE", `${ep(id)}/music/${pid}`),
  applySeries: (id: string, name: string) => req<MusicView>("POST", `${ep(id)}/music/series/apply`, { name }),
  saveSeries: (id: string, name: string) => req<MusicView>("POST", `${ep(id)}/music/series/save`, { name }),
  dismissSeries: (id: string) => req<MusicView>("POST", `${ep(id)}/music/series/dismiss`),
  placementPreviewUrl: (id: string, pid: string) => `${ep(id)}/music/${pid}/preview?t=${Date.now()}`,
};
