import { useEffect, useRef, useState } from "react";

/** Fetch-once cache of per-version chunks (waveform tiles, transcript stretches); re-renders on arrival. */
export function useChunks<T>(version: string, keys: number[], load: (k: number) => Promise<T>): Map<number, T> {
  const cache = useRef(new Map<string, T | null>());
  const [, bump] = useState(0);
  const sig = keys.join(",");
  useEffect(() => {
    let live = true;
    for (const k of keys) {
      const key = `${version}:${k}`;
      if (cache.current.has(key)) continue;
      cache.current.set(key, null);
      load(k).then(
        (v) => {
          cache.current.set(key, v);
          if (live) bump((n) => n + 1);
        },
        () => cache.current.delete(key),
      );
    }
    if (cache.current.size > 400) {
      for (const key of [...cache.current.keys()]) if (!key.startsWith(`${version}:`)) cache.current.delete(key);
    }
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version, sig]);
  const out = new Map<number, T>();
  for (const k of keys) {
    const v = cache.current.get(`${version}:${k}`);
    if (v) out.set(k, v);
  }
  return out;
}

export const range = (a: number, b: number) => Array.from({ length: Math.max(0, b - a + 1) }, (_, i) => a + i);
