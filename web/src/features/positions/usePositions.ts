import { useEffect, useRef } from "react";
import type { Player } from "../../usePlayer";

// Where Leon was editing (Leon 2026-10-30): 整集试听 keeps its own place on the timeline, so coming from 审阅 at
// 49:00 does not drop it at 49:00 (it is where he last was there, from the start the first time), and a refresh,
// leaving the episode and coming back all return to that place. 审阅改动 moves the player to the edit it shows,
// as before. Kept in this browser per episode, in voice-cut seconds of the version on screen.
const PAGES = ["listen"];
const key = (id: string) => `lacuna.pos.${id}`;

function read(id: string): Record<string, number> {
  try {
    const v = JSON.parse(localStorage.getItem(key(id)) ?? "{}");
    return v && typeof v === "object" ? v : {};
  } catch {
    return {};
  }
}

function write(id: string, v: Record<string, number>) {
  try {
    localStorage.setItem(key(id), JSON.stringify(v));
  } catch {
    /* private mode */
  }
}

/** `resume()`: where the page opened first should start (once; null when it has no place of its own). */
export function usePositions(id: string, mode: string, player: Player) {
  const saved = useRef<Record<string, number> | null>(null);
  saved.current ??= read(id);
  const shown = useRef(mode);
  const started = useRef(false);

  // another page: remember this one's place, go to that one's (from the start when it has none yet)
  useEffect(() => {
    const was = shown.current;
    if (was === mode) return;
    shown.current = mode;
    if (PAGES.includes(was)) saved.current![was] = player.time;
    if (PAGES.includes(mode)) player.seek(saved.current![mode] ?? 0);
    write(id, saved.current!);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

  // keep the place while playing, clicking, cutting (the server maps it onto each new version)
  const sec = Math.floor(player.time);
  useEffect(() => {
    if (!started.current || !PAGES.includes(mode) || shown.current !== mode) return;
    saved.current![mode] = player.time;
    write(id, saved.current!);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sec]);

  return {
    resume: (): number | null => {
      if (started.current) return null;
      started.current = true;
      return PAGES.includes(mode) ? (saved.current![mode] ?? null) : null;
    },
  };
}
