import { useCallback, useEffect, useRef, useState } from "react";
import type { Episode } from "../../api";
import type { Player } from "../../usePlayer";
import { t } from "../../i18n";
import { manualApi } from "./api";

/** A selected stretch of the timeline (seconds). `from` says where it was made (its bar shows there);
 *  `speakers`: the hosts whose words were selected in the transcript (all hosts for a waveform drag). */
export interface Sel {
  a: number;
  b: number;
  from: "lanes" | "text";
  speakers?: string[];
  text?: string;
}

export const MIN_SEL = 0.05; // seconds; a shorter drag is a click

/** The manual-editing selection shared by the waveform timeline and the transcript (decision manual-editing). */
export function useManual(ep: Episode | null, player: Player, run: (p: Promise<Episode>, msg?: string) => Promise<boolean>) {
  const [sel, setSel] = useState<Sel | null>(null);
  const [busy, setBusy] = useState(false);
  const stopAt = useRef<number | null>(null);
  const id = ep?.id;

  useEffect(() => setSel(null), [ep?.version]); // a new cut moves everything after it

  const cut = useCallback(
    async (track: string | null) => {
      if (!sel || busy || !id) return;
      setBusy(true);
      const s = (sel.b - sel.a).toFixed(1);
      const ok = await run(
        manualApi.cut(id, sel.a, sel.b, track, Math.max(0, sel.a - 2)),
        track ? t("已静音 {track} {s} 秒，可撤销", { track, s }) : t("已删掉 {s} 秒，可撤销", { s }),
      );
      setBusy(false);
      if (ok) setSel(null);
    },
    [sel, busy, run, id],
  );

  // While something is selected, playing (▶, Space, 听选中) plays only the selection, like an audio editor
  // (Leon 2026-10-20): from its start, or from the playhead when that is already inside it, and at its end the
  // playhead goes back to the start (no rewind-on-pause), ready to hear it again.
  const selRef = useRef(sel);
  selRef.current = sel;
  const now = useRef(player.time); // voice-cut time (the audio element runs on the music mix's clock when it is on)
  now.current = player.time;
  const seekRef = useRef(player.seek);
  seekRef.current = player.seek;
  useEffect(() => {
    if (!sel) stopAt.current = null;
  }, [sel]);
  useEffect(() => {
    const a = player.ref.current;
    if (!a) return;
    const onPlay = () => {
      const s = selRef.current;
      if (!s) return;
      stopAt.current = s.b;
      if (now.current < s.a - 0.02 || now.current >= s.b - 0.05) seekRef.current(s.a);
    };
    a.addEventListener("play", onPlay);
    return () => a.removeEventListener("play", onPlay);
  }, [player.ref, ep?.id]);
  const listen = useCallback(() => {
    if (!sel) return;
    player.seek(sel.a);
    player.play();
  }, [sel, player]);
  useEffect(() => {
    const s = selRef.current;
    if (stopAt.current !== null && s && player.time >= stopAt.current) {
      stopAt.current = null;
      player.ref.current?.pause();
      seekRef.current(s.a);
    }
  }, [player.time, player.ref]);

  // Delete / Backspace cuts the selection from every track, Esc drops it
  useEffect(() => {
    if (!sel) return;
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key === "Delete" || e.key === "Backspace") {
        e.preventDefault();
        void cut(null);
      } else if (e.key === "Escape") setSel(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [sel, cut]);

  return { sel, setSel, cut, listen, busy };
}

export type Manual = ReturnType<typeof useManual>;
