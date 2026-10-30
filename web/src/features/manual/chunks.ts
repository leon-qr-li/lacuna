import { useEffect, useRef, useState } from "react";

/** wait before asking again for chunks that did not come, and how many times */
const AGAIN_MS = 1500;
const TRIES = 4;

/** Fetch-once cache of per-version chunks (waveform tiles, transcript stretches); re-renders on arrival. A chunk
 *  that failed or timed out is asked for again a moment later (Leon 2026-10-30: past 4:45 both lanes stayed
 *  empty until he switched pages, the tiles' answers lost on a dropped connection). */
/** `keepOld`: until a chunk of a new version arrives, show that chunk of the version before (the waveform
 *  does not blink empty after each cut; what the cut moved settles a moment later). */
export function useChunks<T>(version: string, keys: number[], load: (k: number) => Promise<T>, keepOld = false): Map<number, T> {
  const cache = useRef(new Map<string, T | null>());
  const [, bump] = useState(0);
  const [again, setAgain] = useState(0);
  const failed = useRef(new Map<string, number>());
  const sig = keys.join(",");
  const versions = useRef<[string, string | null]>([version, null]); // [now, before]
  if (versions.current[0] !== version) versions.current = [version, versions.current[0]];
  useEffect(() => {
    let live = true;
    for (const k of keys) {
      const key = `${version}:${k}`;
      if (cache.current.has(key) || (failed.current.get(key) ?? 0) >= TRIES) continue;
      cache.current.set(key, null);
      load(k).then(
        (v) => {
          cache.current.set(key, v);
          if (live) bump((n) => n + 1);
        },
        () => {
          cache.current.delete(key);
          failed.current.set(key, (failed.current.get(key) ?? 0) + 1);
          window.setTimeout(() => setAgain((n) => n + 1), AGAIN_MS);
        },
      );
    }
    if (cache.current.size > 400) {
      for (const key of [...cache.current.keys()]) if (!key.startsWith(`${version}:`)) cache.current.delete(key);
      failed.current.clear();
    }
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version, sig, again]);
  const out = new Map<number, T>();
  for (const k of keys) {
    const before = versions.current[1];
    const v = cache.current.get(`${version}:${k}`) ?? (keepOld && before ? cache.current.get(`${before}:${k}`) : null);
    if (v) out.set(k, v);
  }
  return out;
}

export const range = (a: number, b: number) => Array.from({ length: Math.max(0, b - a + 1) }, (_, i) => a + i);
