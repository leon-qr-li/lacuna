import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import type { AB, ABSide } from "../api";

type Side = "before" | "after";

export interface ABHandle {
  toggle: () => void;
  select: (s: Side) => void;
  stop: () => void;
}

/** Map a position in one rendering to the same moment in the other, relative to the edit. */
function mapOffset(t: number, from: ABSide, to: ABSide): number {
  const rel = t - from.edit_at;
  let out: number;
  if (rel <= 0) out = to.edit_at + rel;
  else if (rel >= from.edit_len) out = to.edit_at + to.edit_len + (rel - from.edit_len);
  else out = to.edit_at + Math.min(rel, to.edit_len);
  return Math.max(0, Math.min(out, to.duration));
}

interface Props {
  ab: AB | null;
  labels: [string, string];
  loading?: boolean;
  onPlay?: () => void;
  dark?: boolean;
}

export const ABPlayer = forwardRef<ABHandle, Props>(function ABPlayer({ ab, labels, loading, onPlay, dark }, ref) {
  const audio = useRef<HTMLAudioElement>(null);
  const [side, setSide] = useState<Side | null>(null);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    audio.current?.pause();
    setSide(null);
  }, [ab]);

  const start = useCallback(
    (s: Side) => {
      const a = audio.current;
      if (!a || !ab) return;
      const target = ab[s];
      let at = Math.max(0, target.edit_at - 5);
      if (side && side !== s && !a.paused) at = mapOffset(a.currentTime, ab[side], target);
      a.src = target.url;
      a.preservesPitch = true;
      const go = () => {
        a.currentTime = at;
        void a.play().catch(() => undefined);
      };
      a.addEventListener("loadedmetadata", go, { once: true });
      a.load();
      setSide(s);
      onPlay?.();
    },
    [ab, side, onPlay],
  );

  const toggle = useCallback(() => {
    const a = audio.current;
    if (!a) return;
    if (!side) start("after");
    else if (a.paused) void a.play();
    else a.pause();
  }, [side, start]);

  useImperativeHandle(ref, () => ({ toggle, select: start, stop: () => audio.current?.pause() }), [toggle, start]);

  const btn = (s: Side, label: string, key: string) => (
    <button
      type="button"
      className={`btn ${dark ? "btn-ondark" : "btn-outline"} ${side === s ? "is-on" : ""}`}
      aria-pressed={side === s}
      disabled={!ab || loading}
      onClick={() => (side === s && playing ? audio.current?.pause() : start(s))}
      title={`快捷键 ${key}`}
    >
      {side === s && playing ? "❚❚" : "▶"} {label}
    </button>
  );

  return (
    <div className="ab" role="group" aria-label="前后对比试听">
      {btn("before", labels[0], "A")}
      {btn("after", labels[1], "B")}
      <span className="muted small">{loading ? "正在渲染…" : "前后各约 10 秒，切换时位置同步"}</span>
      <audio
        ref={audio}
        data-testid="ab-audio"
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
      />
    </div>
  );
});
