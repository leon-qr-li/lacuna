// API of 入门 (lacuna_app/routes/onboarding.py): progress per person, kept on the server, and LACUNA 示例节目.
import { useEffect, useState } from "react";
import { req } from "../../api";

export interface Onboarding {
  welcomed: boolean;
  /** the bubble tour of the sample show: the step to come back to, "" when finished or left, null not started */
  tour: string | null;
  /** you were invited into someone else's show and have none of your own */
  collab: { show: string; by: string } | null;
  sample: { id: string; lang: string; episode: string } | null;
}

export const onboardingApi = {
  get: () => req<Onboarding>("GET", "/api/onboarding"),
  flags: (f: { welcomed?: boolean; tour?: string }) => req<Onboarding>("PUT", "/api/onboarding", f),
  addSample: (lang: string) => req<Onboarding>("POST", "/api/onboarding/sample", { lang }),
  resetSample: () => req<Onboarding>("POST", "/api/onboarding/sample/reset"),
  dropSample: () => req<Onboarding>("DELETE", "/api/onboarding/sample"),
};

// one copy for every part of the screen (welcome page, tour, 设置)
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

/** Into the sample show (made the first time), at its episode's review page. */
export async function openSample(lang: string, mode = "review") {
  const o = await onboardingApi.addSample(lang);
  window.location.hash = `#/ep/${encodeURIComponent(o.sample?.episode ?? "SAMPLE_01")}/${mode}`;
  window.location.reload();
}
