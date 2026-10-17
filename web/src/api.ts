export type EditStatus = "applied" | "restored" | "proposed" | "discarded";

export interface EditInfo {
  id: string;
  category: string;
  category_label: string;
  title: string;
  reason: string;
  confidence: number;
  consequential: boolean;
  status: EditStatus;
  approved: boolean;
  source: "first_cut" | "chat" | "manual";
  t: number; // timeline seconds of the edit point
  len: number; // seconds removed / affected
  tracks: string[] | null;
  raw: [number, number] | null; // raw recording seconds
  op_id?: string | null; // AI editor op this edit came from
  ai_category?: string | null;
  speech_s?: number; // seconds of speech removed
}

export interface Proposal {
  id: string;
  title: string;
  message: string;
  target: string;
  state: string;
  edit?: EditInfo;
}

export interface Episode {
  id: string;
  title: string;
  demo: boolean;
  demo_note: string;
  sample_rate: number;
  duration: number;
  raw_duration: number;
  version: string;
  audio_url: string;
  can_undo: boolean;
  can_redo: boolean;
  undo_label: string | null;
  redo_label: string | null;
  tracks: { name: string; gain_db: number; clips: [number, number][] }[];
  topics: { title: string; start: number; end: number }[];
  edits: EditInfo[];
  routine: { category: string; label: string; count: number; seconds: number; restored: number }[];
  pending_review: number;
  review: string[]; // ids of edits that need Leon's judgement, in review order
  proposals: Proposal[];
  has_transcript: boolean;
  playhead?: number;
}

export interface EpisodeListItem {
  id: string;
  title: string;
  demo?: boolean;
  duration?: number;
  raw_duration?: number;
  pending_review?: number;
  error?: string;
}

export interface ABSide {
  url: string;
  start: number;
  edit_at: number;
  edit_len: number;
  duration: number;
}
export interface AB {
  before: ABSide;
  after: ABSide;
}

export interface Usage {
  model: string;
  input_tokens: number;
  output_tokens: number;
  seconds: number;
  cost_usd: number;
}

export interface ChatReply {
  reply: string;
  notes?: string[];
  adapter: string;
  proposal: Proposal | null;
  usage?: Usage | null;
}

export interface Health {
  ok: boolean;
  editor: string; // "claude" | "mock"
  editor_note: string; // why it is not Claude, if not
  dictation?: boolean; // local voice input available
  dictation_note?: string; // why not, if not
}

export interface Dictated {
  text: string;
  audio_s: number;
  seconds: number;
}

export interface TextLine {
  speaker: string;
  words: { t: string; removed: boolean }[];
}

export interface ExportReport {
  input_lufs: number | null;
  input_true_peak_db: number | null;
  output_lufs: number | null;
  output_true_peak_db: number | null;
  comp_mean_gr_db: number | null;
  comp_max_gr_db: number | null;
  limiter_active_pct: number | null;
  duration_s: number;
}

export interface ExportJob {
  id: string;
  state: "running" | "done" | "error";
  progress: number;
  stage: string;
  version: string;
  basename: string;
  error: string | null;
  result: {
    files: Record<string, string>;
    report: ExportReport;
    mp3: { kbps?: number; lufs?: number | null; true_peak_db?: number | null };
    errors: Record<string, string>;
    folder: string;
  } | null;
}

export interface ImportTrack {
  path: string;
  name: string;
  duration: number | null;
  sample_rate: number | null;
}

export interface ImportJob {
  id: string;
  title: string;
  tracks: { L: ImportTrack; P: ImportTrack };
  state: "queued" | "running" | "done" | "error" | "interrupted" | "cancelled";
  progress: number;
  step: string | null;
  stage: string;
  created: string;
  started: string | null;
  run_started?: string;
  finished: string | null;
  elapsed_s?: number;
  error: string | null;
  result: { episode: string; edits: number; to_review: number; raw_duration: number; engine: string } | null;
}

export interface FsListing {
  path: string;
  parent: string | null;
  dirs: { name: string; path: string }[];
  files: { name: string; path: string; size: number; duration: number | null }[];
  roots: string[];
}

export interface LearnedRule {
  id: string;
  kind: string;
  title: string;
  detail: string;
  prompt: string;
  key: Record<string, string | number>;
  evidence: Record<string, unknown>;
  examples: { text: string; raw: [number, number] | null; verdict: string; episode: string; reason: string }[];
  policy: { review?: boolean; confidence?: number } | null;
  state: "candidate" | "approved" | "rejected";
  updated: boolean;
  stale?: boolean;
  approved_at: string | null;
}

export interface LearningOverview {
  rules: LearnedRule[];
  pending: number;
  stats: {
    episodes: string[];
    decisions: number;
    considered: number;
    kept: number;
    restored: number;
    accepted: number;
    declined: number;
    added: number;
    untouched: number;
  };
}

export interface PublishChapter {
  t: number;
  time: string;
  heading: string;
}

export interface PublishName {
  heard: string;
  suggested: string;
  why: string;
  state: "open" | "applied" | "ignored";
}

export interface PublishPack {
  title: string;
  alt_titles: string[];
  blurb: string;
  markdown: string;
  edited: boolean;
  chapters: PublishChapter[];
  names: PublishName[];
  stale: boolean;
  gone: string[];
  notes: string[];
  adapter: string;
  usage: Partial<Usage>;
  generated_at: string;
  library: boolean;
}

export interface PublishJob {
  state: "running" | "done" | "error";
  stage: string;
  started: number;
  finished: number | null;
  error: string | null;
}

export interface PublishView {
  pack: PublishPack | null;
  job: PublishJob | null;
  notes_path: string;
  editor: string;
  editor_note: string;
}

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

export interface Asset {
  id: string;
  kind: "music" | "jingle" | "clip";
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
  kinds: Record<string, string>;
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

async function req<T>(method: string, url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      msg = (await res.json()).detail ?? msg;
    } catch {
      /* not JSON */
    }
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return res.json() as Promise<T>;
}

const ep = (id: string) => `/api/episodes/${encodeURIComponent(id)}`;

async function dictate(audio: Blob): Promise<Dictated> {
  const res = await fetch("/api/dictation", {
    method: "POST",
    headers: { "Content-Type": audio.type || "application/octet-stream" },
    body: audio,
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
  return res.json() as Promise<Dictated>;
}

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
    last_update: { at: string; ok: boolean; message: string } | null;
  };
}

export const api = {
  dictate,
  appInfo: () => req<AppInfo>("GET", "/api/app"),
  checkUpdate: () => req<AppInfo>("POST", "/api/app/update/check"),
  prepareUpdate: () => req<AppInfo>("POST", "/api/app/update/prepare"),
  applyUpdate: () => req<{ restarting: boolean; version: string }>("POST", "/api/app/update/apply"),
  saveApiKey: (key: string) =>
    req<{ saved: boolean; where: string; restarting: boolean }>("POST", "/api/app/api-key", { key }),
  dictationWarm: () => req<{ ok: boolean }>("POST", "/api/dictation/warm"),
  health: () => req<Health>("GET", "/api/health"),
  episodes: () => req<{ episodes: EpisodeListItem[]; editor: string }>("GET", "/api/episodes"),
  episode: (id: string) => req<Episode>("GET", ep(id)),
  editAB: (id: string, eid: string) => req<AB>("GET", `${ep(id)}/edits/${eid}/ab`),
  editText: (id: string, eid: string) => req<{ lines: TextLine[] }>("GET", `${ep(id)}/edits/${eid}/text`),
  review: (id: string, eid: string, action: "keep" | "restore" | "apply", playhead: number) =>
    req<Episode>("POST", `${ep(id)}/edits/${eid}/review`, { action, playhead }),
  reviewAll: (id: string, action: "approve" | "keep" | "restore", playhead: number, ids?: string[]) =>
    req<Episode & { changed: number }>("POST", `${ep(id)}/review`, { action, playhead, ids }),
  undo: (id: string, playhead: number) => req<Episode>("POST", `${ep(id)}/undo`, { playhead }),
  redo: (id: string, playhead: number) => req<Episode>("POST", `${ep(id)}/redo`, { playhead }),
  chat: (id: string, text: string, playhead: number) =>
    req<ChatReply>("POST", `${ep(id)}/chat`, { text, playhead }),
  proposalAB: (id: string, pid: string) => req<AB>("GET", `${ep(id)}/proposals/${pid}/ab`),
  approve: (id: string, pid: string, playhead: number) =>
    req<Episode>("POST", `${ep(id)}/proposals/${pid}/approve`, { playhead }),
  discard: (id: string, pid: string, playhead: number) =>
    req<Episode>("POST", `${ep(id)}/proposals/${pid}/discard`, { playhead }),
  startExport: (id: string, formats: string[]) => req<{ job: ExportJob }>("POST", `${ep(id)}/export`, { formats }),
  exportStatus: (id: string) => req<{ job: ExportJob | null }>("GET", `${ep(id)}/export`),
  imports: () => req<{ jobs: ImportJob[]; next_id: string }>("GET", "/api/imports"),
  startImport: (body: { id: string; title: string; leon: string; pei: string }) =>
    req<{ job: ImportJob }>("POST", "/api/imports", body),
  resumeImport: (id: string) => req<{ job: ImportJob }>("POST", `/api/imports/${encodeURIComponent(id)}/resume`),
  cancelImport: (id: string) => req<{ job: ImportJob }>("POST", `/api/imports/${encodeURIComponent(id)}/cancel`),
  forgetImport: (id: string) => req<{ ok: boolean }>("DELETE", `/api/imports/${encodeURIComponent(id)}`),
  fs: (path?: string) => req<FsListing>("GET", `/api/fs${path ? `?path=${encodeURIComponent(path)}` : ""}`),
  learning: () => req<LearningOverview>("GET", "/api/learning"),
  decideRule: (id: string, action: "approve" | "reject" | "reset") =>
    req<LearningOverview>("POST", "/api/learning/rules", { id, action }),
  library: () => req<LibraryView>("GET", "/api/library"),
  addAsset: (path: string, kind: string, note: string) =>
    req<{ asset: Asset }>("POST", "/api/library/files", { path, kind, note }),
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
  openExports: (id: string) => req<{ folder: string }>("POST", `${ep(id)}/exports/open`),
  publish: (id: string) => req<PublishView>("GET", `${ep(id)}/publish`),
  generatePublish: (id: string) => req<PublishView>("POST", `${ep(id)}/publish/generate`),
  retimePublish: (id: string) => req<PublishView>("POST", `${ep(id)}/publish/retime`),
  editPublish: (id: string, body: { markdown?: string | null; title?: string }) =>
    req<PublishView>("PUT", `${ep(id)}/publish`, body),
  publishName: (id: string, heard: string, action: "apply" | "ignore") =>
    req<PublishView>("POST", `${ep(id)}/publish/names`, { heard, action }),
};

export function fmt(s: number): string {
  if (!isFinite(s) || s < 0) s = 0;
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  const mm = h ? String(m).padStart(2, "0") : String(m);
  return `${h ? h + ":" : ""}${mm}:${String(sec).padStart(2, "0")}`;
}

/** "45:59", "1:02:03", "75" or "75.5" -> seconds; null when unreadable. */
export function parseTime(s: string): number | null {
  const t = s.trim();
  if (!t) return null;
  const parts = t.split(/[:：]/).map((x) => Number(x));
  if (parts.some((x) => !isFinite(x) || x < 0)) return null;
  return parts.reduce((acc, x) => acc * 60 + x, 0);
}

export function statusLabel(e: EditInfo): string {
  if (e.status === "restored") return e.approved ? "已恢复原样" : "AI 未应用，等你决定";
  if (e.source !== "first_cut") return "聊天修改 · 已批准";
  if (e.approved) return "已确认保留";
  return e.consequential ? "待你过目" : "常规清理 · 已自动应用";
}

export function confidenceLabel(c: number): string {
  return c >= 0.8 ? "高" : c >= 0.6 ? "中" : "低";
}
