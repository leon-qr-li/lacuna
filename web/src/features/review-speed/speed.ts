/**
 * Playback speed of the review A/B player (backlog item 6) and the music page's mix player (验收 V8):
 * 1× / 1.25× / 1.5× / 2×, pitch kept, each player's choice remembered in this browser.
 */
import { useCallback, useState } from "react";

export const RATES = [1, 1.25, 1.5, 2] as const;
const KEY = "lacuna.reviewRate";

function read(key: string): number {
  try {
    const v = Number(localStorage.getItem(key));
    return (RATES as readonly number[]).includes(v) ? v : 1;
  } catch {
    return 1;
  }
}

/** The rate after `r` in the cycle (wraps 2× back to 1×). */
export const nextRate = (r: number): number => RATES[(RATES.indexOf(r as (typeof RATES)[number]) + 1) % RATES.length];

export const rateLabel = (r: number): string => `${r}×`;

export const useReviewRate = () => useRate(KEY);

/** A speed remembered under `key` (localStorage). */
export function useRate(key: string) {
  const [rate, setState] = useState(() => read(key));
  const setRate = useCallback((r: number) => {
    setState(r);
    try {
      localStorage.setItem(key, String(r));
    } catch {
      /* storage unavailable: the choice lasts for this page only */
    }
  }, [key]);
  const cycle = useCallback(() => setRate(nextRate(rate)), [rate, setRate]);
  return { rate, setRate, cycle };
}
