// 「带配乐听」 in the review player: the main <audio> plays the final mix (voice + music) instead of the
// voice cut. Everything else on the page (lanes, edits, chat, undo) keeps speaking voice-cut time, so the
// player is wrapped: its time is mapped back onto the voice cut, seeks are mapped onto the mix.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Player } from "../../usePlayer";
import type { MusicView } from "./api";
import { libraryApi } from "./api";
import { fmt } from "../../api";

const KEY = "lacuna.listenWithMusic";
const EPS = 1e-4;

type Inserts = [number, number][]; // (voice seconds, inserted seconds), sorted

/** Voice-cut seconds -> final-mix seconds (material at an insert point comes after the gap). */
export function toFinal(ins: Inserts, v: number): number {
  return v + ins.reduce((s, [T, n]) => (T <= v + EPS ? s + n : s), 0);
}

/** Final-mix seconds -> voice-cut seconds (inside inserted music: its insert point). */
export function toVoice(ins: Inserts, f: number): number {
  let shift = 0;
  for (const [T, n] of ins) {
    const start = T + shift;
    if (f < start) break;
    if (f < start + n) return T;
    shift += n;
  }
  return f - shift;
}

function readPref(): boolean {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

export interface MusicListen {
  player: Player; // voice-cut time, whichever stream plays
  on: boolean;
  available: boolean; // the episode has music
  finalTime: number;
  setOn: (v: boolean) => void;
}

/** `refresh` changes whenever the voice cut or the music may have changed (edit version, page). */
export function useMusicListen(id: string, refresh: string, raw: Player): MusicListen {
  const [music, setMusic] = useState<MusicView | null>(null);
  const [on, setOnState] = useState(readPref);
  const voiceUrl = useRef<string | null>(null);
  const want = useRef<number | null>(null); // voice time to resume at once the right stream is known
  const shown = useRef<string | null>(null);

  useEffect(() => {
    let live = true;
    libraryApi
      .music(id)
      .then((m) => live && setMusic(m))
      .catch(() => live && setMusic(null));
    return () => {
      live = false;
    };
  }, [id, refresh]);

  const available = !!music && music.placements.some((p) => !p.missing && p.start_s != null);
  const active = on && available;
  const ins: Inserts = useMemo(() => (active && music ? music.inserts ?? [] : []), [active, music]);
  const time = active ? toVoice(ins, raw.time) : raw.time;
  const timeRef = useRef(time);
  timeRef.current = time;

  // play the right stream; keep the voice-cut position across switches and new versions
  useEffect(() => {
    const url = active ? music!.mix_url : voiceUrl.current;
    if (!url || url === shown.current) return;
    const v = want.current ?? timeRef.current;
    want.current = null;
    shown.current = url;
    raw.load(url, active ? toFinal(ins, v) : v);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, music?.mix_url, ins]);

  const load = useCallback(
    (url: string, at: number) => {
      const same = url === voiceUrl.current;
      voiceUrl.current = url;
      if (active) {
        if (same) raw.seek(toFinal(ins, at));
        else want.current = at; // the mix for this version arrives with the next music fetch
        return;
      }
      shown.current = url;
      raw.load(url, at);
    },
    [active, ins, raw],
  );

  const seek = useCallback((t: number) => raw.seek(active ? toFinal(ins, t) : t), [active, ins, raw]);

  const setOn = useCallback(
    (v: boolean) => {
      want.current = timeRef.current;
      setOnState(v);
      try {
        localStorage.setItem(KEY, v ? "1" : "0");
      } catch {
        /* storage unavailable */
      }
    },
    [],
  );

  const player = useMemo<Player>(() => ({ ...raw, time, load, seek }), [raw, time, load, seek]);
  return { player, on: active, available, finalTime: active ? raw.time : toFinal(music?.inserts ?? [], raw.time), setOn };
}

export function MusicListenToggle({ listen }: { listen: MusicListen }) {
  if (!listen.available) return null;
  return (
    <label className="check music-listen" title="播放加了配乐的成品；审阅、对话里的时间仍按人声剪辑算">
      <input type="checkbox" checked={listen.on} onChange={(e) => listen.setOn(e.target.checked)} data-testid="listen-with-music" />
      带配乐听
      {listen.on && <span className="mono small"> · 成品 {fmt(listen.finalTime)}</span>}
    </label>
  );
}

