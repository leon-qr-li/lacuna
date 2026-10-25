// The import form's state lives here, not in the form (batch 5, decision 2026-10-24-upload-and-queue): the
// tracks keep uploading while you look at another page, and the form comes back as you left it. Only 取消
// (or a replaced file) lets an upload go. Leaving or reloading the page while a file is still uploading asks
// first, and so does switching to another show (features/projects/api.ts).
import { useSyncExternalStore } from "react";
import type { Host, Language } from "../show/api";
import { importApi, uploadTrack, type PickedTrack } from "./api";

/** A host's track slot, by the host's tag (lacuna_app/show.py). */
export type Who = string;
/** One track slot: a file being sent to the server, or one it has. */
export interface Slot {
  key: object;
  name: string;
  progress: number;
  size: number;
  track?: PickedTrack;
  error?: string;
  abort?: () => void;
}

export interface Draft {
  id: string;
  title: string;
  language: Language;
  album: string;
  hosts: Host[];
  slots: Record<Who, Slot | null>;
  /** a message about the files dropped (more files than hosts) */
  note: string | null;
}

let draft: Draft | null = null;
let shown = 0; // forms on screen now (the top-bar progress hides while one is)
const subs = new Set<() => void>();
const emit = () => subs.forEach((f) => f());
const subscribe = (f: () => void) => {
  subs.add(f);
  return () => {
    subs.delete(f);
  };
};

export const useDraft = () => useSyncExternalStore(subscribe, () => draft);
export const useFormShown = () => useSyncExternalStore(subscribe, () => shown > 0);

/** The form opened on screen (`on`) or closed: while none is, the top bar shows the uploads. */
export function formOnScreen(on: boolean) {
  shown += on ? 1 : -1;
  emit();
}

/** Open the form (it keeps what is already in it). */
export function openDraft(d: Omit<Draft, "slots" | "note">) {
  if (!draft) draft = { ...d, slots: Object.fromEntries(d.hosts.map((h) => [h.tag, null])), note: null };
  emit();
}

export function patch(p: Partial<Pick<Draft, "id" | "title" | "language" | "album" | "note">>) {
  if (!draft) return;
  draft = { ...draft, ...p };
  emit();
}

const setSlot = (who: Who, fn: (s: Slot | null) => Slot | null) => {
  if (!draft) return;
  draft = { ...draft, slots: { ...draft.slots, [who]: fn(draft.slots[who] ?? null) } };
  emit();
};

export function swap(a: Who, b: Who) {
  if (!draft) return;
  draft = { ...draft, slots: { ...draft.slots, [a]: draft.slots[b], [b]: draft.slots[a] } };
  emit();
}

const letGo = (s: Slot | null) => {
  s?.abort?.();
  if (s?.track) void importApi.removeTrack(s.track.path).catch(() => undefined);
};

/** 取消: the uploads stop and the server drops the files it got. */
export function discard() {
  if (draft) Object.values(draft.slots).forEach(letGo);
  draft = null;
  emit();
}

/** The import started: the server has the files now, the form goes. */
export function finish() {
  draft = null;
  emit();
}

/** Send `file` as `who`'s track (one already there is let go). */
export function put(who: Who, file: File) {
  if (!draft) return;
  letGo(draft.slots[who] ?? null);
  const key = {}; // this upload, so a late answer for a replaced file is ignored
  const mine = () => draft?.slots[who]?.key === key;
  const up = uploadTrack(file, (p) => mine() && !draft!.slots[who]!.track && setSlot(who, (s) => ({ ...s!, progress: p })));
  setSlot(who, () => ({ key, name: file.name, progress: 0, size: file.size, abort: up.abort }));
  up.done
    .then((track) => {
      if (!mine()) return void importApi.removeTrack(track.path).catch(() => undefined);
      setSlot(who, () => ({ key, name: file.name, progress: 1, size: file.size, track }));
    })
    .catch((e: Error) => {
      if (e.name !== "AbortError" && mine()) setSlot(who, () => ({ key, name: file.name, progress: 0, size: file.size, error: e.message }));
    });
}

/** Which slot each dropped file belongs to: by a host's name in the file name ("Leon.wav"), else the
 *  free slots in order. `hosts`: [tag, name] of every slot. */
export function assign(files: File[], free: Who[], hosts: Host[]): [Who, File][] {
  const out = new Map<Who, File>();
  const rest: File[] = [];
  // longer names first, so "Anna" wins over "Ann" in "anna.wav"
  const byName = [...hosts].filter((h) => h.name.trim().length >= 2).sort((a, b) => b.name.length - a.name.length);
  for (const f of files) {
    const n = f.name.toLowerCase();
    const who = byName.find((h) => n.includes(h.name.trim().toLowerCase()) && !out.has(h.tag))?.tag;
    if (who) out.set(who, f);
    else rest.push(f);
  }
  const order = [...free, ...hosts.map((h) => h.tag).filter((w) => !free.includes(w))];
  for (const f of rest) {
    const who = order.find((w) => !out.has(w));
    if (who) out.set(who, f);
  }
  return [...out];
}

/** Files dropped or picked: onto one slot (`only`), else each to its host. Returns how many were left out. */
export function add(files: File[], only?: Who): number {
  if (!draft) return 0;
  if (only) {
    if (files[0]) put(only, files[0]);
    return 0;
  }
  const hosts = draft.hosts;
  const free = hosts.map((h) => h.tag).filter((w) => !draft!.slots[w]);
  for (const [who, f] of assign(files.slice(0, hosts.length), free, hosts)) put(who, f);
  return Math.max(0, files.length - hosts.length);
}

/** Tracks still on their way to the server. */
export function uploading(): Slot[] {
  return draft ? Object.values(draft.slots).filter((s): s is Slot => !!s && !s.track && !s.error) : [];
}

/** How far the uploads are, 0..1, by bytes. */
export function uploadProgress(): number {
  const up = uploading();
  const total = up.reduce((n, s) => n + s.size, 0);
  return total ? up.reduce((n, s) => n + s.size * s.progress, 0) / total : 0;
}

// leaving or reloading while a track is still uploading: the browser asks first
if (typeof window !== "undefined")
  window.addEventListener("beforeunload", (e) => {
    if (uploading().length) {
      e.preventDefault();
      e.returnValue = "";
    }
  });
