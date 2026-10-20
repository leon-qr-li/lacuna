import type { Episode } from "../api";
import { t } from "../i18n";

/** Whole-episode strip: topics (if known) and where the edits are. Click to jump. */
export function Overview({ ep, time, onSeek }: { ep: Episode; time: number; onSeek: (t: number) => void }) {
  const d = ep.duration || 1;
  const pct = (t: number) => `${(100 * t) / d}%`;
  const jump = (e: React.MouseEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    onSeek(((e.clientX - r.left) / r.width) * d);
  };
  return (
    <section className="card" aria-label={t("整集概览")}>
      <div className="card-head">
        <h2>{ep.topics.length ? t("话题段落") : t("整集概览")}</h2>
        <span className="muted small">
          {ep.topics.length ? t("点击跳转") : t("深色刻度 = 需要你过目的改动 · 点击跳转")}
        </span>
      </div>
      {ep.topics.length > 0 && (
        <div className="topics">
          {ep.topics.map((t) => (
            <button
              key={t.start}
              type="button"
              className="topic"
              style={{ flexGrow: Math.max(t.end - t.start, 1) }}
              onClick={() => onSeek(t.start)}
            >
              {t.title}
            </button>
          ))}
        </div>
      )}
      <div className="overview" onClick={jump} role="presentation">
        {ep.edits
          .filter((e) => e.category !== "loudness")
          .map((e) => (
            <span
              key={e.id}
              className={`tick ${e.consequential ? "major" : ""} ${e.status === "restored" ? "restored" : ""}`}
              style={{ left: pct(e.t) }}
            />
          ))}
        <span className="ov-head" style={{ left: pct(time) }} />
      </div>
    </section>
  );
}
