// Spaces between transcript words: only where both sides of the seam are Latin, so Chinese reads as
// before and English words don't run together (same rule as lacuna_app/words.py).
const NO_SPACE_BEFORE = new Set([...",.;:!?)]}%'\""]);
const latin = (c: string | undefined) => c !== undefined && c >= "!" && c <= "~";

/** Whether a space goes between `prev` and `next` (two words, or longer pieces of text). */
export function needsSpace(prev: string, next: string): boolean {
  return latin(prev[prev.length - 1]) && latin(next[0]) && !NO_SPACE_BEFORE.has(next[0]);
}
