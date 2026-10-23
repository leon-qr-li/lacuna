// API of 入门 (lacuna_app/routes/onboarding.py): progress per person, kept on the server, and LACUNA 示例节目.
import { useEffect, useState } from "react";
import { req } from "../../api";
import { loadProjects } from "../projects/api";

export type Step = "show" | "import" | "review" | "chat" | "music" | "export";
export type SampleStep = "ab" | "decide" | "chat" | "music" | "export";

export interface Onboarding {
  /** steps done; those in the sample show start with "sample." */
  done: string[];
  hidden: boolean;
  welcomed: boolean;
  /** the bubble tour of the sample show: the step to come back to, "" when finished or left, null not started */
  tour: string | null;
  /** the steps of your own first episode (the short version for a collaborator: review, chat) */
  steps: Step[];
  sample_steps: SampleStep[];
  /** you were invited into someone else's show and have none of your own */
  collab: { show: string; by: string } | null;
  sample: { id: string; lang: string; episode: string } | null;
}

export const onboardingApi = {
  get: () => req<Onboarding>("GET", "/api/onboarding"),
  mark: (step: string) => req<Onboarding>("POST", "/api/onboarding/mark", { step }),
  flags: (f: { hidden?: boolean; welcomed?: boolean; tour?: string }) => req<Onboarding>("PUT", "/api/onboarding", f),
  addSample: (lang: string) => req<Onboarding>("POST", "/api/onboarding/sample", { lang }),
  resetSample: () => req<Onboarding>("POST", "/api/onboarding/sample/reset"),
  dropSample: () => req<Onboarding>("DELETE", "/api/onboarding/sample"),
};

// one copy for every part of the screen (home card, top-bar tag, coach panel)
let cache: Onboarding | null | undefined;
let pending: Promise<Onboarding | null> | null = null;
const subs = new Set<(o: Onboarding | null) => void>();

export function setOnboarding(o: Onboarding | null) {
  cache = o;
  subs.forEach((f) => f(o));
}

function load(): Promise<Onboarding | null> {
  if (cache !== undefined) return Promise.resolve(cache);
  pending ??= onboardingApi
    .get()
    .catch(() => null)
    .then((o) => {
      pending = null;
      setOnboarding(o);
      return o;
    });
  return pending;
}

/** undefined while loading, null without accounts (a desktop install: no guide). */
export function useOnboarding(): Onboarding | null | undefined {
  const [o, set] = useState<Onboarding | null | undefined>(cache);
  useEffect(() => {
    subs.add(set);
    void load();
    return () => {
      subs.delete(set);
    };
  }, []);
  return o;
}

/** Something real happened (a download, an edit looked at …): tick that step of the guide. In the sample show
 *  it ticks the coach's step instead. Quiet: the guide never gets in the way of the work. */
export function markStep(step: Step | SampleStep) {
  void Promise.all([load(), loadProjects()]).then(([o, sp]) => {
    if (!o) return;
    const key = sp?.current?.sample ? `sample.${step}` : step;
    if (o.done.includes(key)) return;
    setOnboarding({ ...o, done: [...o.done, key] });
    onboardingApi.mark(key).then(setOnboarding, () => undefined);
  });
}

/** A note kept with the guide's progress, e.g. "card.<show id>": 节目资料卡 put away for that show. */
export function markDone(key: string) {
  void load().then((o) => {
    if (!o || o.done.includes(key)) return;
    setOnboarding({ ...o, done: [...o.done, key] });
    onboardingApi.mark(key).then(setOnboarding, () => undefined);
  });
}

/** Into the sample show (made the first time), at its episode's review page. */
export async function openSample(lang: string, mode = "review") {
  const o = await onboardingApi.addSample(lang);
  window.location.hash = `#/ep/${encodeURIComponent(o.sample?.episode ?? "SAMPLE_01")}/${mode}`;
  window.location.reload();
}
