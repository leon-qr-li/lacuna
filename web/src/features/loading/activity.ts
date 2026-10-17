/**
 * Counts requests the person started (anything but GET) so the top bar can show a thin moving line
 * while one is in flight. Polls and page loads are GETs and show their own placeholders instead.
 */
type Listener = (n: number) => void;
let inflight = 0;
const listeners = new Set<Listener>();
const emit = () => listeners.forEach((l) => l(inflight));

export function track<T>(p: Promise<T>): Promise<T> {
  inflight++;
  emit();
  return p.finally(() => {
    inflight--;
    emit();
  });
}

export function subscribe(l: Listener): () => void {
  listeners.add(l);
  l(inflight);
  return () => listeners.delete(l);
}
