// API of the confirmed-learning feature (首次检测 #9, #12): 「记住」 drafts and 本集学到的规则
import type { ChatReply } from "../../api";
import { ep, req } from "../../api";

/** LACUNA's reading of what Leon asked to remember; a rule only after 记住这条. */
export interface RememberDraft {
  id: string;
  said: string;
  at: number;
  title: string;
  understood: string;
  instruction: string;
  same_as: string;
  same_as_title: string;
  fallback: boolean; // no AI: his own words, for him to confirm or change
  state: "pending" | "confirmed" | "dropped";
  rule?: string;
}

/** A chat reply to 「记住」 carries the draft. */
export type RememberReply = ChatReply & { remember?: RememberDraft };

export interface LessonTurn {
  turn: number;
  said: string;
  at: number;
  reply: string;
}

export interface LessonEdit {
  edit: string;
  verdict: "kept" | "restored" | "accepted" | "declined" | "added";
  kind: string;
  host: string;
  text: string;
  seconds: number;
  raw: [number, number] | null;
}

export interface Lesson {
  id: string;
  title: string;
  instruction: string;
  why: string;
  relation: "new" | "reinforce" | "conflict";
  related: string;
  related_title: string;
  turns: LessonTurn[];
  edits: LessonEdit[];
  state: "draft" | "adopted" | "skipped";
  edited: boolean;
  reply: string; // LACUNA's answer to his last correction
  fallback?: boolean;
  rule?: string;
  rule_state?: string | null;
}

export interface LessonsView {
  state: "none" | "running" | "done" | "error" | "no_key" | "demo";
  at: string | null;
  error: string | null;
  stale: boolean; // more chat or review since the summary
  lessons: Lesson[];
  pending: number;
}

const base = (id: string) => `${ep(id)}/lessons`;

export const lessonsApi = {
  decideDraft: (id: string, did: string, action: "confirm" | "drop") =>
    req<RememberDraft>("POST", `${ep(id)}/remember/${did}`, { action }),
  reviseDraft: (id: string, did: string, text: string) =>
    req<RememberDraft>("POST", `${ep(id)}/remember/${did}/revise`, { text }),
  view: (id: string) => req<LessonsView>("GET", base(id)),
  run: (id: string) => req<LessonsView>("POST", `${base(id)}/run`),
  decide: (id: string, lid: string, action: "adopt" | "skip" | "reopen") =>
    req<Lesson>("POST", `${base(id)}/${lid}`, { action }),
  edit: (id: string, lid: string, text: string) => req<Lesson>("POST", `${base(id)}/${lid}/edit`, { text }),
  revise: (id: string, lid: string, text: string) => req<Lesson>("POST", `${base(id)}/${lid}/revise`, { text }),
};
