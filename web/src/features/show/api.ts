// The workspace's show (lacuna_app/show.py, routes/show.py): name, hosts, how LACUNA presents it.
import { useEffect, useState } from "react";
import { req } from "../../api";
import { joinList, t } from "../../i18n";

export type HostColor = "blue" | "purple" | "teal" | "amber" | "green" | "pink";
export type CutLevel = "gentle" | "normal" | "firm";
/** what the hosts speak: picks the speech recognisers and LACUNA's editing brief (lacuna_app/asr.py) */
export type Language = "zh" | "en";
export const LANGUAGES: Language[] = ["zh", "en"];
export const LANGUAGE_LABELS: Record<Language, string> = {
  zh: t("中文"),
  en: t("英文"),
};

export interface Host {
  /** one letter, given by the server; never changes (empty for a host not saved yet) */
  tag: string;
  name: string;
  color: HostColor;
  cut_level: CutLevel;
  style: string;
}

export interface Show {
  show_name: string;
  about: string;
  language: Language;
  footer: string;
  hosts: Host[];
  publish: { ximalaya: boolean; album: string };
  legacy: boolean;
  needs_setup: boolean;
  colors: HostColor[];
  cut_levels: CutLevel[];
  max_hosts: number;
}

export type ShowInput = Pick<Show, "show_name" | "about" | "language" | "footer" | "hosts" | "publish">;

export const showApi = {
  get: () => req<Show>("GET", "/api/show"),
  save: (s: ShowInput) => req<Show>("PUT", "/api/show", s),
};

// one copy for the whole page: the top bar, the colours and every view read the same profile
let current: Show | null = null;
let loading: Promise<Show | null> | null = null;
const listeners = new Set<(s: Show | null) => void>();

function publish(s: Show | null) {
  current = s;
  applyColors(s);
  listeners.forEach((f) => f(s));
}

/** Loads the profile once (again after `setShow` / a failed load). */
export function loadShow(): Promise<Show | null> {
  if (current) return Promise.resolve(current);
  loading ??= showApi
    .get()
    .then((s) => (publish(s), s))
    .catch(() => null)
    .finally(() => {
      loading = null;
    });
  return loading;
}

export function setShow(s: Show) {
  publish(s);
}

/** The current workspace's show, or null while it loads (or when nobody is signed in). */
export function useShow(): Show | null {
  const [s, set] = useState<Show | null>(current);
  useEffect(() => {
    listeners.add(set);
    void loadShow();
    return () => {
      listeners.delete(set);
    };
  }, []);
  return s;
}

/** --host-N = the N-th host's colour (show.css), so tracks, transcripts and meters follow the show. */
function applyColors(s: Show | null) {
  const root = document.documentElement.style;
  (s?.hosts ?? []).forEach((h, i) => {
    root.setProperty(`--host-${i}`, `var(--c-${h.color})`);
    root.setProperty(`--host-${i}-ink`, `var(--c-${h.color}-ink)`);
  });
}

export const hostNames = (s: Show | null) => (s?.hosts ?? []).map((h) => h.name);

/** The hosts' names as a phrase: "Leon 和 Pei", "A、B 和 C" ("" while the show loads). */
export function hostList(s: Show | null): string {
  const n = hostNames(s);
  return n.length < 2 ? (n[0] ?? "") : t("{list} 和 {last}", { list: joinList(n.slice(0, -1)), last: n[n.length - 1] });
}
