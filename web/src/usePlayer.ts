import { useCallback, useEffect, useRef, useState } from "react";

const REWIND_KEY = "lacuna.rewindOnPause";

/** 暂停时回退 5 秒 is off until the user ticks it (Leon 2026-10-20). */
function readPref(): boolean {
  try {
    return localStorage.getItem(REWIND_KEY) === "1";
  } catch {
    return false;
  }
}

/** Full-listen player around one <audio> element. The source is a streamed WAV of the current
 *  edit version; switching version keeps the (server-mapped) position and play state. */
export function usePlayer() {
  const ref = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [rate, setRateState] = useState(1);
  const [rewindOnPause, setRewindState] = useState(readPref);
  const pendingSeek = useRef<number | null>(null);

  const el = () => ref.current;

  useEffect(() => {
    const a = el();
    if (!a) return;
    a.preservesPitch = true; // 1.5x without chipmunk voices
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    const onTime = () => {
      // once the seek has landed, or playback has moved on from it, the position is the element's own
      const p = pendingSeek.current;
      if (p !== null && (Math.abs(a.currentTime - p) <= 0.05 || (!a.paused && a.currentTime > p))) pendingSeek.current = null;
      setTime(pendingSeek.current ?? a.currentTime);
    };
    // A seek right after a source switch can be dropped (clamped to 0) while the stream is not yet
    // seekable, so the pending position is re-applied on each loading event until it sticks.
    const applyPending = () => {
      const p = pendingSeek.current;
      if (p === null || a.readyState === 0) return;
      if (Math.abs(a.currentTime - p) > 0.05) a.currentTime = p;
      if (Math.abs(a.currentTime - p) <= 0.05) pendingSeek.current = null;
      setTime(p);
    };
    const onMeta = () => {
      a.playbackRate = a.defaultPlaybackRate;
      applyPending();
    };
    a.addEventListener("play", onPlay);
    a.addEventListener("pause", onPause);
    a.addEventListener("timeupdate", onTime);
    a.addEventListener("seeked", onTime);
    a.addEventListener("loadedmetadata", onMeta);
    const retry = ["loadeddata", "canplay", "progress", "durationchange"] as const;
    retry.forEach((ev) => a.addEventListener(ev, applyPending));
    return () => {
      retry.forEach((ev) => a.removeEventListener(ev, applyPending));
      a.removeEventListener("play", onPlay);
      a.removeEventListener("pause", onPause);
      a.removeEventListener("timeupdate", onTime);
      a.removeEventListener("seeked", onTime);
      a.removeEventListener("loadedmetadata", onMeta);
    };
  }, []);

  // smooth playhead while playing (timeupdate only fires ~4x per second)
  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    const tick = () => {
      const a = el();
      if (a) setTime(a.currentTime);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing]);

  const load = useCallback((url: string, at: number) => {
    const a = el();
    if (!a) return;
    const resume = !a.paused;
    if (a.getAttribute("src") === url) {
      // still loading: a seek now can be dropped, so apply it on loadedmetadata instead
      if (a.readyState === 0 || pendingSeek.current !== null) pendingSeek.current = at;
      if (a.readyState > 0 && Math.abs(a.currentTime - at) > 0.05) a.currentTime = at;
      setTime(at);
      return;
    }
    pendingSeek.current = at;
    a.src = url;
    a.load();
    setTime(at);
    if (resume) void a.play().catch(() => undefined);
  }, []);

  const play = useCallback(() => {
    void el()?.play().catch(() => undefined);
  }, []);

  const pause = useCallback(() => {
    const a = el();
    if (!a || a.paused) return;
    a.pause();
    if (rewindOnPause) a.currentTime = Math.max(0, a.currentTime - 5);
  }, [rewindOnPause]);

  const toggle = useCallback(() => (el()?.paused ? play() : pause()), [play, pause]);

  const seek = useCallback((t: number) => {
    const a = el();
    if (!a) return;
    const d = isFinite(a.duration) ? a.duration : t;
    const v = Math.max(0, Math.min(t, d));
    if (a.readyState === 0 || pendingSeek.current !== null) pendingSeek.current = v;
    if (a.readyState > 0) a.currentTime = v;
    if (pendingSeek.current !== null && Math.abs(a.currentTime - v) <= 0.05) pendingSeek.current = null;
    setTime(v);
  }, []);

  const skip = useCallback((d: number) => seek((el()?.currentTime ?? 0) + d), [seek]);

  const setRate = useCallback((r: number) => {
    const a = el();
    if (a) {
      a.preservesPitch = true;
      a.defaultPlaybackRate = r;
      a.playbackRate = r; // changing rate never moves the position
    }
    setRateState(r);
  }, []);

  const setRewindOnPause = useCallback((v: boolean) => {
    setRewindState(v);
    try {
      localStorage.setItem(REWIND_KEY, v ? "1" : "0");
    } catch {
      /* storage unavailable */
    }
  }, []);

  return { ref, playing, time, rate, rewindOnPause, load, play, pause, toggle, seek, skip, setRate, setRewindOnPause };
}

export type Player = ReturnType<typeof usePlayer>;
