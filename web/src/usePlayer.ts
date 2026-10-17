import { useCallback, useEffect, useRef, useState } from "react";

const REWIND_KEY = "lacuna.rewindOnPause";

function readPref(): boolean {
  try {
    return localStorage.getItem(REWIND_KEY) !== "0";
  } catch {
    return true;
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
    const onTime = () => setTime(a.currentTime);
    const onMeta = () => {
      a.playbackRate = a.defaultPlaybackRate;
      if (pendingSeek.current !== null) {
        a.currentTime = pendingSeek.current;
        setTime(pendingSeek.current);
        pendingSeek.current = null;
      }
    };
    a.addEventListener("play", onPlay);
    a.addEventListener("pause", onPause);
    a.addEventListener("timeupdate", onTime);
    a.addEventListener("seeked", onTime);
    a.addEventListener("loadedmetadata", onMeta);
    return () => {
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
      if (Math.abs(a.currentTime - at) > 0.05) a.currentTime = at;
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
    if (a.readyState === 0) pendingSeek.current = v;
    else a.currentTime = v;
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
