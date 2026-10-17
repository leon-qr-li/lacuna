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

export const api = {
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
  learning: () => req<LearningOverview>("GET", "/api/learning"),
  decideRule: (id: string, action: "approve" | "reject" | "reset") =>
    req<LearningOverview>("POST", "/api/learning/rules", { id, action }),
  openExports: (id: string) => req<{ folder: string }>("POST", `${ep(id)}/exports/open`),
};

export function fmt(s: number): string {
  if (!isFinite(s) || s < 0) s = 0;
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  const mm = h ? String(m).padStart(2, "0") : String(m);
  return `${h ? h + ":" : ""}${mm}:${String(sec).padStart(2, "0")}`;
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
