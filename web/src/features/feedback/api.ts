// API of 用户反馈 (lacuna_app/routes/feedback.py)
import { req } from "../../api";

export type Kind = "bug" | "idea" | "praise";
export type Status = "received" | "working" | "planned" | "fixed" | "shipped" | "declined";
export type Importance = "nice" | "need" | "fine";

export interface Context {
  page?: string;
  title?: string;
  episode?: string;
  /** playhead, seconds */
  at?: number;
  lang?: string;
  error?: string;
  error_code?: string;
  /** the last steps in the app (features/feedback/trail.ts) */
  actions?: string[];
}

export interface Mine {
  id: string;
  created: number;
  kind: Kind;
  status: Status;
  /** an answer the person hasn't looked at yet (the red dot) */
  unread: boolean;
  text: string;
  shot: boolean;
  show: { id: string; name: string } | null;
  episode?: string;
  replies: { text: string; at: number }[];
  adopted: boolean;
  bonus_hours: number;
}

export interface MineList {
  items: Mine[];
  unread: number;
}

export interface NewFeedback {
  kind: Kind;
  text: string;
  source: "button" | "error" | "publish";
  context: Context;
  importance?: Importance;
  quote_ok?: boolean;
  platforms?: string[];
  /** data:image/jpeg;base64,… */
  shot?: string;
}

export type PromptKind = "rate" | "pmf";

export const feedbackApi = {
  send: (body: NewFeedback) => req<MineList & { id: string }>("POST", "/api/feedback", body),
  mine: () => req<MineList>("GET", "/api/feedback/mine"),
  seen: () => req<MineList>("POST", "/api/feedback/mine/seen"),
  due: () => req<{ ask: PromptKind | null }>("GET", "/api/feedback/prompt"),
  answer: (kind: PromptKind, outcome: "sent" | "later" | "never", answer?: Record<string, unknown>) =>
    req<{ ok: boolean }>("POST", "/api/feedback/prompt", { kind, outcome, answer: answer ?? {} }),
  /** the current show's two optional questions (its language is the show's own setting) */
  profile: (a: { region?: string; editing?: string }) => req<Record<string, string>>("POST", "/api/feedback/profile", a),
};
