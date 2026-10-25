// What the admin API answers (lacuna_app/admin_api.py, admin_metrics.py). Times are Unix seconds.
export type Role = "owner" | "admin" | "member";

export interface Me {
  email: string;
  name: string | null;
  role: Role;
  lang: string | null;
  exp: number;
  stepup: number;
  owner: string | null;
  now: number;
}

export interface Alert {
  level: "bad" | "warn" | "info";
  kind: "disk" | "ai" | "backup" | "imports" | "errors" | "maintenance" | "capacity";
  line?: string; // capacity: what it is now, and what to do (in the reader's language)
  advice?: string;
  measure?: CapacityMeasure["key"];
  pct?: number;
  used?: number;
  total?: number;
  spent?: number;
  budget?: number;
  at?: number;
  n?: number;
}

export interface Activity {
  ts: number;
  ev: string;
  who: string | null;
  name: string | null;
  show: string | null;
  ep: string | null;
}

export interface Kpi {
  value: number;
  delta: number;
  spark: number[];
}

export interface CapacityMeasure {
  key: "disk" | "queue" | "hours" | "memory" | "people";
  level: "ok" | "warn" | "act" | "urgent";
  line: string;
  advice: string;
}

export interface Overview {
  todo: { fb: number; hours: number; trial: number; collab: number };
  alerts: Alert[];
  kpi: {
    accounts: Kpi;
    wau: Kpi;
    exports: Kpi;
    ai: { value: number; forecast: number; budget: number; spark: number[] };
    disk: { value: number; used: number; total: number };
  };
  wau: number[];
  ai: { spent: number; forecast: number; days: number; cumulative: number[]; budget: number };
  activity: Activity[];
  capacity?: CapacityMeasure[];
}

export type FbStatus = "received" | "working" | "planned" | "fixed" | "shipped" | "declined";

export interface FbItem {
  id: string;
  created: number;
  email: string;
  kind: "bug" | "idea" | "praise";
  status: FbStatus;
  unread: boolean;
  text: string;
  source: string | null;
  shot: boolean;
  show: { id: string; name: string } | null;
  context: { page?: string; title?: string; episode?: string; lang?: string; error?: string; browser?: string; actions?: string[]; at?: number };
  importance: string | null;
  quote_ok: boolean | null;
  platforms: string[];
  replies: { text: string; at: number }[];
  adopted: boolean;
  bonus_hours: number;
  version: string | null;
  profile: { region?: string; editing?: string; lang?: string } | null;
  name: string | null;
  plan: string | null;
  joined: number | null;
  tags: string[];
  notes: number;
}

export interface Template {
  id: string;
  title: string;
  text: string;
}

export interface FeedbackData {
  items: FbItem[];
  statuses: FbStatus[];
  templates: Template[];
  known_tags: string[];
}

export interface Prompts {
  rate: Record<string, number>;
  saved: Record<string, number>;
  pmf: Record<string, number>;
  nps: { scores: Record<string, number>; n: number; score: number | null; promoters: number; passives: number; detractors: number };
  quotes: { kind: string; at: number; email: string; name: string | null; text: string; stars?: number; choice?: string; score?: number }[];
  profiles: { n: number; region: Record<string, number>; editing: Record<string, number>; lang: Record<string, number> };
}

export interface Note {
  id: string;
  target: string;
  ts: number;
  email: string;
  text: string;
}

export interface UserRow {
  email: string;
  name: string | null;
  role: Role;
  plan: string;
  free: boolean;
  created: number;
  disabled: boolean;
  twofa: boolean;
  last: number | null;
  lang: string | null;
  silent: boolean;
  shows: number;
  made: number;
  episodes: number;
  ai: number;
  size: number;
  source: string | null;
  invited_by: string | null;
  hours_used: number | null;
  hours: number | null;
}

export interface PlanLimits {
  id: string;
  name: string;
  hours: number | null;
  hours_once: boolean;
  shows: number | null;
  collaborators: number | null;
}

export interface HourReq {
  id: string;
  email: string;
  created: number;
  status: "new" | "approved" | "declined";
  hours: number;
  reason: string;
  would_pay: boolean;
  granted?: number;
  decided_by?: string;
  decided_at?: number;
  name?: string | null;
  plan?: string | null;
}

export interface UserDetail {
  user: UserRow;
  shows: { id: string; name: string; role: string; episodes?: number; people?: number; updated?: number; archived?: boolean; sample?: boolean }[];
  activity: { ts: number; ev: string; ep: string | null; show: string | null; props: Record<string, unknown> }[];
  sessions: { created: number; seen: number; device: string }[];
  devices: number;
  notes: Note[];
  hours: HourReq[];
  feedback: FbItem[];
  bonus_hours: number;
}

export interface AccessReq {
  id: string;
  email: string;
  show: string;
  note: string;
  created: number;
  lang?: string | null;
  tracks?: string | null;
  kind?: string;
  space?: string;
  space_role?: string;
  by?: string;
  by_name?: string | null;
  status: string;
}

export interface Invite {
  id: string;
  email: string;
  role: Role;
  by: string;
  plan: string;
  created: number;
  exp: number;
  space: string | null;
  source: string | null;
}

export interface AccessData {
  trials: AccessReq[];
  collabs: AccessReq[];
  waitlist: AccessReq[];
  invites: Invite[];
  seats: { used: number; total: number };
  approval: boolean;
  sources: { source: string; invited: number; joined: number; week4: number }[];
  source_ids: string[];
  link?: string;
  mailed?: boolean;
  mail_error?: string | null;
}

export interface QuotaRules {
  enforce: boolean;
  must_fit: boolean;
  staff_exempt: boolean;
  repeat_free: boolean;
}

export interface HoursData {
  requests: HourReq[];
  decided: HourReq[];
  usage: {
    email: string;
    name: string | null;
    plan: string;
    hours: number | null;
    used: number | null;
    /** extra hours this month (approved requests, adopted feedback) */
    bonus?: { granted: number; feedback: number } | null;
    /** the trial: one allowance, ever */
    once?: boolean;
  }[];
  plans: PlanLimits[];
  beta_end: string | null;
  /** the metering rules (lacuna_app/quota.py); null where the site doesn't meter */
  quota?: QuotaRules | null;
  /** audio hours every show imported this month (the server's work) */
  month_hours?: number | null;
  willing: { email: string; name: string | null; at: number; reason: string; where: string }[];
}

export interface ShowRow {
  id: string;
  name: string;
  creator: string | null;
  members: number;
  episodes: number;
  created: number;
  last: number | null;
  size: number | null;
  archived: boolean;
  sample: boolean;
  support: number | null;
  language: string | null;
}

export interface ShowsData {
  shows: ShowRow[];
  stuck: { sid: string; show: string; ep: string; last: number; who: string | null; ev: string; why: "failed" | "idle" }[];
  votes: Record<string, number>;
  voters: number;
  sizes_at: number | null;
}

export interface TrashData {
  items: { kind: "show" | "user"; id: string; name: string; by: string | null; deleted_at: number; left_days: number; size?: number | null }[];
  keep_days: number;
}

export interface AiData {
  spent: number;
  forecast: number;
  days: number;
  cumulative: number[];
  budget: number;
  month: string;
  per_hour: number | null;
  target: number;
  hours: number;
  features: Record<string, number>;
  top: { email: string; name: string | null; cost: number; hours: number; per_hour: number | null }[];
  fails: { imports: number; refusals: number };
  accuracy: { category: string; kept: number | null; n: number }[];
  rules_month: number;
  calls: number;
}

export interface GrowthData {
  wau: number[];
  signups: number[];
  activation: { rate: number | null; of: number; n: number };
  per_user_month: number | null;
  active_month: number;
  langs: Record<string, number>;
  funnel: { step: string; n: number }[];
  durations: { from: string; to: string; median: number | null; n: number }[];
  features: { feature: string; pct: number | null }[];
  cohorts: { start: number; size: number; weeks: (number | null)[] }[];
  regions: Record<string, number>;
}

export interface SystemData {
  disk: { used: number; total: number; pct: number };
  parts: Record<string, number>;
  sizes_at: number | null;
  backup: { at: number | null; snapshot: number | null };
  running: { sid: string; show: string; kind: string; episode: string; state: string; progress: number | null; started: number | null }[];
  samples: { ts: number; cpu: number | null; mem: number | null }[];
  errors: { method: string; path: string; status: number; n: number; last: number }[];
  started: number;
  version: string;
  alerts: Alert[];
  cpus: number;
  storage?: StorageData;
  ai?: AiSettings;
}

export interface AiSettings {
  first_cut_batch: boolean;
}

export interface StorageData {
  retention: { raw_tracks: boolean; old_exports: boolean };
  cold: { on: boolean; moving: boolean; bytes: number; after_days: number };
}

export interface SettingsData {
  notice: { on: boolean; zh: string; en: string; until: string | null };
  maintenance: { on: boolean };
  staff: { email: string; name: string | null; role: Role; twofa: boolean; last_admin: number | null }[];
  sessions: { id: string; email: string; created: number; exp: number; agent?: string; country?: string | null; seen?: number; current: boolean }[];
  terms: string[];
  mail: { configured: boolean; source: string | null; sender: string };
  key: { present: boolean; source: string | null };
  turnstile: boolean;
  access: boolean | null;
  cloud: boolean;
  digest: { hour: number; tz: string; last: string | null };
  budget: number;
}

export interface AuditRow {
  id: number;
  ts: number;
  email: string;
  action: string;
  target: string;
  data: Record<string, unknown>;
}
