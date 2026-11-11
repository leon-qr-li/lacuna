import { fmt } from "../api";
import type { Player } from "../usePlayer";
import { t } from "../i18n";

export function PlayerBar({ player, duration }: { player: Player; duration: number }) {
  const { playing, time, rate } = player;
  return (
    <section className="player" aria-label={t("播放器")}>
      <button type="button" className="btn btn-ondark sq" aria-label={t("后退 5 秒")} onClick={() => player.skip(-5)}>
        {t("−5 秒")}
      </button>
      <button
        type="button"
        className="play"
        aria-label={playing ? t("暂停") : t("播放")}
        data-testid="play"
        onClick={player.toggle}
      >
        {playing ? "❚❚" : "▶"}
      </button>
      <button type="button" className="btn btn-ondark sq" aria-label={t("前进 5 秒")} onClick={() => player.skip(5)}>
        {t("+5 秒")}
      </button>
      <span className="mono" data-testid="clock" aria-live="off">
        {fmt(time)} / {fmt(duration)}
      </span>
      <label className="seek">
        <span className="sr-only">{t("播放位置")}</span>
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
      <div role="group" aria-label={t("播放速度")} className="rates">
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
        {t("暂停时回退 5 秒")}
      </label>
    </section>
  );
}
