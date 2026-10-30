import { t } from "./i18n";
import { track } from "./features/loading/activity";
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
  room_tone?: boolean; // one host's sound erased and filled with their own room tone
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
  /** goes up at every change of the episode, by anyone (co-editing, features/coedit) */
  rev?: number;
}

export interface EpisodeListItem {
  id: string;
  title: string;
  demo?: boolean;
  duration?: number;
  raw_duration?: number;
  pending_review?: number;
  error?: string;
  /** the chosen cover's preview, null: none chosen (the tile shows its letter) */
  poster?: string | null;
  /** exported at least once (the tile's status stripe) */
  exported?: boolean;
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
  raw?: string; // what the local recogniser heard, before the context pass
  corrected?: boolean;
}

/** What the context pass may use to fix names and homophones (text only, never audio). */
export interface DictationContext {
  episode?: string;
  at?: number; // playhead seconds
  where?: "chat" | "poster";
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
  music_version?: string;
  music_stale?: boolean; // the episode's music changed after this export
  basename: string;
  started?: number;
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
  tracks: Record<string, ImportTrack>; // by host tag
  hosts?: [string, string][]; // [tag, name] in order (older imports: Leon + Pei)
  language?: string; // zh / en (older imports: zh)
  state: "queued" | "running" | "done" | "error" | "interrupted" | "cancelled";
  progress: number;
  step: string | null;
  steps?: Record<string, unknown>; // finished steps, by importer STEPS key
  stage: string;
  created: string;
  started: string | null;
  run_started?: string;
  finished: string | null;
  elapsed_s?: number;
  error: string | null;
  result: { episode: string; edits: number; to_review: number; raw_duration: number; engine: string } | null;
}

/** `timeout` (ms): give up on a request that has had no answer by then (`lost` on the error), so a button
 *  never stays greyed out on a connection that went quiet. Only for requests the server answers at once. */
export interface ReqOptions {
  timeout?: number;
}

export async function req<T>(method: string, url: string, body?: unknown, opts: ReqOptions = {}): Promise<T> {
  // anything the person started (not a GET) moves the thin line under the top bar
  return method === "GET" ? send<T>(method, url, body, opts) : track(send<T>(method, url, body, opts));
}

async function send<T>(method: string, url: string, body?: unknown, opts: ReqOptions = {}): Promise<T> {
  const init: RequestInit = {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  };
  try {
    return await attempt<T>(url, init, opts.timeout);
  } catch (e) {
    // "Failed to fetch": no answer at all. On the cloud site that is mostly a connection the browser kept
    // open while the person filled in a form and that Cloudflare had already dropped (net::ERR_QUIC_PROTOCOL_ERROR,
    // Leon 2026-10-30: 新建节目 failed on the first 确认 and worked on the second). The browser then opens a
    // fresh one, so one more try is what the second click did by hand. A request that timed out is not sent
    // again: the server may well have done it (a cut that was made, the answer lost on the way back).
    if (!(e instanceof TypeError)) throw e;
    await new Promise((r) => setTimeout(r, RETRY_MS));
    return attempt<T>(url, init, opts.timeout);
  }
}

/** wait before the one retry of a request that got no answer */
const RETRY_MS = 300;

async function attempt<T>(url: string, init: RequestInit, timeout?: number): Promise<T> {
  const stop = timeout ? new AbortController() : null;
  const timer = stop ? window.setTimeout(() => stop.abort(), timeout) : 0;
  try {
    const res = await fetch(url, stop ? { ...init, signal: stop.signal } : init);
    if (!res.ok) throw await failure(res, url);
    return (await res.json()) as T;
  } catch (e) {
    if (!stop?.signal.aborted) throw e;
    const err: RequestError = new Error(t("网络断了一下，没有收到回应"));
    err.lost = true;
    throw err;
  } finally {
    if (stop) window.clearTimeout(timer);
  }
}

/** A failed request: `status`, and `stale` when the change was refused because someone else changed
 *  the same thing first (co-editing, features/coedit): the page should load the latest. */
export type RequestError = Error & { status?: number; stale?: boolean; lost?: boolean; restoring?: { progress: number; failed: boolean } };

/** The error for a failed request (the server's `detail`); a 401 also brings the sign-in screen
 *  back (features/auth/AuthGate). Every raw fetch of the app goes through this. */
export async function failure(res: Response, url: string): Promise<RequestError> {
  if (res.status === 401 && !url.startsWith("/api/auth/")) window.dispatchEvent(new Event("lacuna:auth"));
  let msg = res.statusText;
  let stale = false;
  let restoring: RequestError["restoring"];
  try {
    const body = await res.json();
    msg = body.detail ?? msg;
    stale = body.stale === true;
    restoring = body.restoring; // 423: the episode's audio is coming back from cloud storage (features/cold)
  } catch {
    /* not JSON */
  }
  const err: RequestError = new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  err.status = res.status;
  if (stale) err.stale = true;
  if (restoring) err.restoring = restoring;
  return err;
}

export const ep = (id: string) => `/api/episodes/${encodeURIComponent(id)}`;

async function dictate(audio: Blob, ctx: DictationContext = {}): Promise<Dictated> {
  const q = new URLSearchParams();
  if (ctx.episode) q.set("episode", ctx.episode);
  if (ctx.at !== undefined && Number.isFinite(ctx.at)) q.set("at", ctx.at.toFixed(2));
  if (ctx.where) q.set("where", ctx.where);
  const qs = q.toString();
  const url = `/api/dictation${qs ? `?${qs}` : ""}`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": audio.type || "application/octet-stream" },
    body: audio,
  });
  if (!res.ok) throw await failure(res, url);
  return res.json() as Promise<Dictated>;
}

export const api = {
  dictate,
  dictationWarm: () => req<{ ok: boolean }>("POST", "/api/dictation/warm"),
  health: () => req<Health>("GET", "/api/health"),
  episode: (id: string) => req<Episode>("GET", ep(id)),
  editAB: (id: string, eid: string) => req<AB>("GET", `${ep(id)}/edits/${eid}/ab`),
  editText: (id: string, eid: string) => req<{ lines: TextLine[] }>("GET", `${ep(id)}/edits/${eid}/text`),
  // `rev`: the episode version on screen; the server refuses (409, stale) when someone else changed it since
  review: (id: string, eid: string, action: "keep" | "restore" | "apply", playhead: number, rev?: number) =>
    req<Episode>("POST", `${ep(id)}/edits/${eid}/review`, { action, playhead, rev }),
  reviewAll: (id: string, action: "approve" | "keep" | "restore", playhead: number, ids?: string[], rev?: number) =>
    req<Episode & { changed: number }>("POST", `${ep(id)}/review`, { action, playhead, ids, rev }),
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
  startImport: (body: { id: string; title: string; tracks: string[]; language?: string; album?: string }) =>
    req<{ job: ImportJob }>("POST", "/api/imports", body),
  resumeImport: (id: string) => req<{ job: ImportJob }>("POST", `/api/imports/${encodeURIComponent(id)}/resume`),
  cancelImport: (id: string) => req<{ job: ImportJob }>("POST", `/api/imports/${encodeURIComponent(id)}/cancel`),
  forgetImport: (id: string) => req<{ ok: boolean }>("DELETE", `/api/imports/${encodeURIComponent(id)}`),
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

/** "45:59", "1:02:03", "75" or "75.5" -> seconds; null when unreadable. */
export function parseTime(s: string): number | null {
  const t = s.trim();
  if (!t) return null;
  const parts = t.split(/[:：]/).map((x) => Number(x));
  if (parts.some((x) => !isFinite(x) || x < 0)) return null;
  return parts.reduce((acc, x) => acc * 60 + x, 0);
}

export function statusLabel(e: EditInfo): string {
  if (e.status === "restored") return e.approved ? t("已恢复原样") : t("LACUNA 未应用，等你决定");
  if (e.source === "manual") return t("手动剪辑");
  if (e.source !== "first_cut") return t("聊天修改 · 已批准");
  if (e.approved) return t("已确认保留");
  return e.consequential ? t("待你审阅") : t("常规清理 · 已自动应用");
}

export function confidenceLabel(c: number): string {
  return c >= 0.8 ? t("高") : c >= 0.6 ? t("中") : t("低");
}
