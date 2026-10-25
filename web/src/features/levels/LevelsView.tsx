import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { Episode } from "../../api";
import { fmt } from "../../api";
import { ABPlayer } from "../../components/ABPlayer";
import type { AB } from "../../api";
import { PlayerBar } from "../../components/PlayerBar";
import { manualApi } from "../manual/api";
import { usePlayer } from "../../usePlayer";
import { t } from "../../i18n";
import { BusyLabel, PageLoading } from "../loading/Loading";
import type { Levels, TrackLevel } from "./api";
import { levelsApi } from "./api";

interface Props {
  id: string;
  ep: Episode;
  flash: (m: string, opts?: { undo?: boolean }) => void;
  onPauseMain: () => void;
  onEpisode?: (ep: Episode) => void;
}

const db = (x: number) =>
  `${x > 0 ? "+" : x < 0 ? "−" : "±"}${Math.abs(x).toFixed(1)} dB`;
const COMMIT_MS = 450; // a slider drag becomes one change once it rests

/** 声音: both hosts at one loudness, a gain per track, and the spots where a recording clipped.
 *  The gains are ordinary undoable edits of the episode (they show up in 撤销 / 重做). */
export function LevelsView({ id, ep, flash, onPauseMain, onEpisode }: Props) {
  const [lv, setLv] = useState<Levels | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null); // track name, "auto" or null
  const player = usePlayer();

  useEffect(() => {
    levelsApi.levels(id).then(setLv, (e) => setErr(String(e.message ?? e)));
  }, [id, ep.version]);

  // a new gain is a new version of the episode: swap the stream and keep listening where we were
  useEffect(() => {
    player.load(ep.audio_url, player.time);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ep.audio_url]);

  useEffect(() => {
    if (player.playing) onPauseMain(); // one player at a time
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [player.playing]);

  const run = async (
    who: string,
    p: () => ReturnType<typeof levelsApi.auto>,
    done?: string,
    undoable?: boolean,
  ) => {
    setBusy(who);
    try {
      const r = await p();
      setLv(r.levels);
      onEpisode?.(r);
      if (done) flash(done, { undo: undoable });
    } catch (e) {
      flash(t("没调成：{message}", { message: (e as Error).message }));
      levelsApi.levels(id).then(setLv, () => undefined);
    } finally {
      setBusy(null);
    }
  };

  const setGain = (track: string, g: number) =>
    run(track, () => levelsApi.setGain(id, track, g, player.time));
  const auto = () =>
    run("auto", () => levelsApi.auto(id, player.time), t("主持人音量已统一"), true);
  const listenAt = (s: number) => {
    player.seek(Math.max(s - 2, 0));
    player.play();
  };

  // usePlayer wires its <audio> on the first render: it stays mounted at the same place throughout
  const audio = (
    <audio ref={player.ref} preload="auto" data-testid="levels-audio" />
  );
  if (err || !lv)
    return (
      <>
        {audio}
        {err ? (
          <p className="error pad">
            {t("声音页打不开：")}
            {err}
          </p>
        ) : (
          <PageLoading label={t("正在测量主持人音量…")} shape="list" />
        )}
      </>
    );

  const spread = (() => {
    const xs = lv.tracks
      .map((x) => x.level_lufs)
      .filter((x): x is number => x !== null);
    return xs.length > 1 ? Math.max(...xs) - Math.min(...xs) : 0;
  })();
  const clipped = lv.tracks.filter((x) => x.clip_count > 0);
  const kept = clipped.some((x) => x.clip_times.length > 0);

  const clipFor = (tr: TrackLevel) =>
    tr.clip_count > 0 ? (
      <div className={`levels-clip small${tr.clip_times.length ? " warn" : ""}`} data-testid={`levels-clips-${tr.name}`}>
        <span className="muted">{t("破音")}</span>
        <span>
          {t("{name}：{n} 处，已自动修复 {r} 处", { name: tr.name, n: tr.clip_count, r: tr.clip_repaired })}
        </span>
        {tr.clip_times.length > 0 && (
          <span className="levels-times">
            <span>
              {t("{n} 处太严重，硬修反而更难听，保持原样；点时间可以从前 2 秒开始听：", { n: tr.clip_kept })}
            </span>
            {tr.clip_times.map((s) => (
              <button key={s} type="button" className="btn btn-small btn-outline" onClick={() => listenAt(s)}>
                {fmt(s)}
              </button>
            ))}
            {tr.clip_kept > tr.clip_times.length && (
              <span className="muted">{t("（只列出前 {n} 处）", { n: tr.clip_times.length })}</span>
            )}
          </span>
        )}
      </div>
    ) : (
      <div className="levels-clip small" data-testid={`levels-clips-${tr.name}`}>
        <span className="muted">{t("破音")}</span>
        <span className="ok">{t("没有破音")}</span>
      </div>
    );

  const solo = lv.tracks.length < 2;
  return (
    <>
      {audio}
      <main className="levels-step" data-testid="levels">
        <section className="levels-card">
          <div className="levels-head">
            <div>
              <h2>{t("主持人音量")}</h2>
              <p className="muted small">
                {solo
                  ? t("这一集只有一位主持人，不用统一。可以在下面单独调音量。")
                  : lv.even
                  ? t(
                      "主持人已经一样响（都在 {target} LUFS 左右），审阅和导出听到的是同一个平衡。",
                      { target: lv.target_lufs },
                    )
                  : t(
                      "主持人现在相差约 {d} dB。点「统一主持人音量」，大家都拉到 {target} LUFS。",
                      { d: spread.toFixed(1), target: lv.target_lufs },
                    )}
              </p>
            </div>
            {!solo && (<button
              type="button"
              className={`btn ${lv.even ? "btn-outline" : "btn-primary"}`}
              onClick={auto}
              disabled={busy !== null}
              data-testid="levels-auto"
              data-tour="levels-auto"
            >
              <BusyLabel
                busy={busy === "auto"}
                label={lv.even ? t("重新统一") : t("统一主持人音量")}
                busyLabel={t("正在统一…")}
              />
            </button>)}
          </div>
          <ul className={`levels-tracks${lv.tracks.length > 2 ? " levels-many" : ""}`}>
            {lv.tracks.map((tr, i) => (
              <TrackRow
                key={tr.name}
                id={id}
                version={ep.version}
                tr={tr}
                idx={i}
                lv={lv}
                busy={busy === tr.name}
                onSet={(g) => setGain(tr.name, g)}
                clip={clipFor(tr)}
              />
            ))}
          </ul>
          {clipped.length > 0 && (
            <p className={`muted small levels-note${kept ? " warn" : ""}`} data-testid="levels-clips">
              {t("原始录音里声音过载被削平的地方（破音），LACUNA 会自动修好：审阅、试听和导出听到的都是修好的声音，原始录音不动。")}
              {kept && <> {t("下次录音时把这条音轨的输入音量调低一点，就不会再破音。")}</>}
            </p>
          )}
          <p className="muted small levels-note" data-tour="levels-chat">
            {t(
              "也可以在「整集试听」里直接对 LACUNA 说「我的声音太低」「{name} 小一点 3 dB」「音量统一一下」。每次调整都能撤销。",
              { name: ep.tracks[ep.tracks.length - 1]?.name ?? "" },
            )}
          </p>
        </section>

        <section className="levels-listen" data-tour="levels-listen">
          <PlayerBar player={player} duration={ep.duration} />
          <Compare id={id} version={ep.version} at={player.time} onPlay={player.pause} />
          <p className="muted small">
            {t(
              "导出时还会对整集做一次响度标准化（−16 LUFS）和轻压缩；这里调的是主持人之间的平衡，以及审阅时听到的音量。",
            )}
          </p>
        </section>
      </main>
    </>
  );
}

/** 原始 / 调整后: the moment under the playhead without and with the volume edits. */
function Compare({ id, version, at, onPlay }: { id: string; version: string; at: number; onPlay: () => void }) {
  const [ab, setAb] = useState<AB | "loading" | null>(null);
  useEffect(() => setAb(null), [version]);
  const load = () => {
    setAb("loading");
    levelsApi.ab(id, at).then(setAb, () => setAb(null));
  };
  return (
    <div className="levels-compare" data-testid="levels-compare">
      <button type="button" className="btn btn-small btn-outline" onClick={load} disabled={ab === "loading"}>
        {t("对比这里：原始 / 调整后")}
      </button>
      {ab && <ABPlayer ab={ab === "loading" ? null : ab} loading={ab === "loading"} labels={[t("原始"), t("调整后")]} onPlay={onPlay} />}
    </div>
  );
}

/** Where the host sits: −30 … −6 LUFS, the recording (tick), now (bar) and the target (green line). */
function Meter({ raw, now, target }: { raw: number | null; now: number | null; target: number }) {
  const lo = -30;
  const hi = -6;
  const p = (v: number) => `${(Math.min(Math.max(v, lo), hi) - lo) / (hi - lo) * 100}%`;
  return (
    <div className="levels-meter" aria-hidden="true">
      <div className="levels-meter-bar">
        {now !== null && <span className="levels-meter-now" style={{ width: p(now) }} />}
        {raw !== null && <span className="levels-meter-raw" style={{ left: p(raw) }} />}
        <span className="levels-meter-target" style={{ left: p(target) }} />
      </div>
      <div className="levels-meter-scale muted">
        <span>{t("−30 轻")}</span>
        <span>
          <span className="levels-key-raw">│</span> {t("原始")} <span className="levels-key-target">│</span> {t("目标 {n}", { n: target })}
        </span>
        <span>{t("响 −6 LUFS")}</span>
      </div>
    </div>
  );
}

/** The first ten seconds of one host before and after the gain (peaks are square-root scaled). */
function Waves({ id, version, name, gain }: { id: string; version: string; name: string; gain: number }) {
  const [pk, setPk] = useState<number[] | null>(null);
  useEffect(() => {
    let live = true;
    // the first 30 seconds (three tiles), so both hosts are in it
    Promise.all([0, 1, 2].map((k) => manualApi.wave(id, version, k).catch(() => null))).then((ws) => {
      if (!live) return;
      const all = ws.flatMap((w) => w?.tracks.find((x) => x.name === name)?.peaks ?? []);
      setPk(all.length ? all : null);
    });
    return () => {
      live = false;
    };
  }, [id, version, name]);
  if (!pk || !pk.length) return null;
  const n = 120;
  const step = pk.length / n;
  const bars = (scale: number) =>
    Array.from({ length: n }, (_, i) => {
      let v = 0;
      for (let k = Math.floor(i * step); k < Math.floor((i + 1) * step); k++) v = Math.max(v, pk[k] ?? 0);
      return <i key={i} style={{ height: `${Math.min(100, Math.max(2, v * scale))}%` }} />;
    });
  const before = 1 / Math.pow(10, gain / 40); // sqrt-scaled peaks: half the dB
  return (
    <div className="levels-waves" aria-hidden="true">
      <span className="muted small">{t("调整前 → 调整后")}</span>
      <div className="levels-wave is-before">{bars(before)}</div>
      <div className="levels-wave">{bars(1)}</div>
    </div>
  );
}

function TrackRow({
  id,
  version,
  tr,
  idx,
  lv,
  busy,
  onSet,
  clip,
}: {
  id: string;
  version: string;
  clip: ReactNode;
  tr: TrackLevel;
  idx: number;
  lv: Levels;
  busy: boolean;
  onSet: (g: number) => void;
}) {
  const [val, setVal] = useState(tr.gain_db);
  const timer = useRef<number | null>(null);
  useEffect(() => setVal(tr.gain_db), [tr.gain_db]);
  useEffect(
    () => () => {
      if (timer.current) window.clearTimeout(timer.current);
    },
    [],
  );

  const clamp = (g: number) =>
    Math.min(Math.max(Math.round(g * 2) / 2, lv.min_db), lv.max_db);
  const commit = (g: number, wait: number) => {
    const v = clamp(g);
    setVal(v);
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      timer.current = null;
      if (Math.abs(v - tr.gain_db) >= 0.05) onSet(v);
    }, wait);
  };
  const heard = tr.lufs !== null ? tr.lufs + val : null;
  const off =
    tr.suggested_gain_db !== null &&
    Math.abs(tr.suggested_gain_db - val) >= 0.5;

  return (
    <li
      className={`levels-track levels-track-${idx % 2}`}
      data-testid={`levels-track-${tr.name}`}
      data-tour={idx === 0 ? "levels-first" : undefined}
    >
      <div className="levels-top" data-tour={idx === 0 ? "levels-meter" : undefined}>
        <div className="levels-name">
          <span className="levels-dot" aria-hidden="true" />
          <strong>{tr.name}</strong>
          <span className="muted small">
            {heard !== null
              ? t("现在 {lufs} LUFS", { lufs: heard.toFixed(1) })
              : t("听不到声音")}
            {tr.lufs !== null && (
              <> · {t("原始 {lufs} LUFS", { lufs: tr.lufs.toFixed(1) })}</>
            )}
          </span>
        </div>
        <Meter raw={tr.lufs} now={heard} target={lv.target_lufs} />
        <Waves id={id} version={version} name={tr.name} gain={val} />
      </div>
      <div className="levels-adjust" data-tour={idx === 0 ? "levels-controls" : undefined}>
        <div className="levels-ctl">
          <span className="muted small">{t("音量")}</span>
          <button
            type="button"
            className="btn btn-small btn-outline sq"
            aria-label={t("{name} 小 1 dB", { name: tr.name })}
            onClick={() => commit(val - 1, 0)}
          >
            −1
          </button>
          <label className="levels-slider">
            <span className="sr-only">
              {t("{name} 的增益", { name: tr.name })}
            </span>
            <input
              type="range"
              min={lv.min_db}
              max={lv.max_db}
              step={0.5}
              value={val}
              aria-valuetext={db(val)}
              onChange={(e) => commit(Number(e.target.value), COMMIT_MS)}
            />
          </label>
          <button
            type="button"
            className="btn btn-small btn-outline sq"
            aria-label={t("{name} 大 1 dB", { name: tr.name })}
            onClick={() => commit(val + 1, 0)}
          >
            +1
          </button>
          <output
            className="levels-val mono"
            data-testid={`levels-gain-${tr.name}`}
          >
            {busy ? "…" : db(val)}
          </output>
        </div>
        <div className="levels-extra small">
          {off && tr.suggested_gain_db !== null ? (
            <button
              type="button"
              className="btn btn-small btn-ghost"
              onClick={() => commit(tr.suggested_gain_db as number, 0)}
            >
              {t("用建议值 {db}", { db: db(tr.suggested_gain_db) })}
            </button>
          ) : (
            tr.suggested_gain_db !== null && <span className="ok">{t("✓ 就是建议值")}</span>
          )}
          {tr.out_peak_db !== null && tr.out_peak_db > -1 && (
            <span className="warn">{t("最响的地方会被轻轻压住")}</span>
          )}
        </div>
      </div>
      <div data-tour={idx === 0 ? "levels-clip" : undefined}>{clip}</div>
    </li>
  );
}
