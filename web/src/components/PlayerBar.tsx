import { fmt } from "../api";
import type { Player } from "../usePlayer";

export function PlayerBar({ player, duration }: { player: Player; duration: number }) {
  const { playing, time, rate } = player;
  return (
    <section className="player" aria-label="播放器">
      <button type="button" className="btn btn-ondark sq" aria-label="后退 5 秒" onClick={() => player.skip(-5)}>
        −5s
      </button>
      <button
        type="button"
        className="play"
        aria-label={playing ? "暂停" : "播放"}
        data-testid="play"
        onClick={player.toggle}
      >
        {playing ? "❚❚" : "▶"}
      </button>
      <button type="button" className="btn btn-ondark sq" aria-label="前进 5 秒" onClick={() => player.skip(5)}>
        +5s
      </button>
      <span className="mono" data-testid="clock" aria-live="off">
        {fmt(time)} / {fmt(duration)}
      </span>
      <label className="seek">
        <span className="sr-only">播放位置</span>
        <input
          type="range"
          min={0}
          max={duration || 0}
          step={0.1}
          value={Math.min(time, duration || 0)}
          aria-valuetext={`${fmt(time)} / ${fmt(duration)}`}
          onChange={(e) => player.seek(Number(e.target.value))}
        />
      </label>
      <div role="group" aria-label="播放速度" className="rates">
        {[1, 1.5].map((r) => (
          <button
            key={r}
            type="button"
            className={`btn btn-ondark ${rate === r ? "is-on" : ""}`}
            aria-pressed={rate === r}
            onClick={() => player.setRate(r)}
          >
            {r}×
          </button>
        ))}
      </div>
      <label className="check">
        <input
          type="checkbox"
          checked={player.rewindOnPause}
          onChange={(e) => player.setRewindOnPause(e.target.checked)}
        />
        暂停时回退 5 秒
      </label>
    </section>
  );
}
