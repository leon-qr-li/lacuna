import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import type { AB, ABSide } from "../api";
import { t } from "../i18n";
import { BusyLabel, Wave } from "../features/loading/Loading";

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
  compact?: boolean; // a segmented A | B pill for the review dock, hint as a tooltip
  rate?: number; // playback speed, pitch kept (review speed picker)
}

export const ABPlayer = forwardRef<ABHandle, Props>(function ABPlayer({ ab, labels, loading, onPlay, dark, compact, rate = 1 }, ref) {
  const audio = useRef<HTMLAudioElement>(null);
  const [side, setSide] = useState<Side | null>(null);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    audio.current?.pause();
    setSide(null);
  }, [ab]);

  // a new speed applies at once, without moving the position
  useEffect(() => {
    const a = audio.current;
    if (!a) return;
    a.preservesPitch = true;
    a.defaultPlaybackRate = rate;
    a.playbackRate = rate;
  }, [rate]);

  const start = useCallback(
    (s: Side) => {
      const a = audio.current;
      if (!a || !ab) return;
      const target = ab[s];
      let at = Math.max(0, target.edit_at - 5);
      if (side && side !== s && !a.paused) at = mapOffset(a.currentTime, ab[side], target);
      a.src = target.url;
      a.preservesPitch = true;
      a.defaultPlaybackRate = rate;
      const go = () => {
        a.playbackRate = rate; // load() resets the rate to defaultPlaybackRate; set both anyway
        a.currentTime = at;
        void a.play().catch(() => undefined);
      };
      a.addEventListener("loadedmetadata", go, { once: true });
      a.load();
      setSide(s);
      onPlay?.();
    },
    [ab, side, onPlay, rate],
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
      className={compact ? `ab-opt ${side === s ? "is-on" : ""}` : `btn ${dark ? "btn-ondark" : "btn-outline"} ${side === s ? "is-on" : ""}`}
      aria-pressed={side === s}
      disabled={!ab || loading}
      onClick={() => (side === s && playing ? audio.current?.pause() : start(s))}
      title={t("快捷键 {key}", { key })}
    >
      {loading ? <Wave /> : side === s && playing ? "❚❚" : "▶"} {label}
    </button>
  );

  return (
    <div
      className={compact ? "ab ab-seg" : "ab"}
      role="group"
      aria-label={t("前后对比试听")}
      title={compact ? (loading ? t("正在渲染…") : t("前后各约 5 秒，切换时位置同步")) : undefined}
    >
      {btn("before", labels[0], "A")}
      {btn("after", labels[1], "B")}
      {!compact && <span className="muted small">{loading ? <BusyLabel busy label={t("正在渲染…")} /> : t("前后各约 5 秒，切换时位置同步")}</span>}
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
