import type { Episode, EditInfo } from "../api";
import { fmt } from "../api";

const WINDOW = 60; // seconds visible in the lane view

/** Whole-episode strip: topics (if known) and where the edits are. Click to jump. */
export function Overview({ ep, time, onSeek }: { ep: Episode; time: number; onSeek: (t: number) => void }) {
  const d = ep.duration || 1;
  const pct = (t: number) => `${(100 * t) / d}%`;
  const jump = (e: React.MouseEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    onSeek(((e.clientX - r.left) / r.width) * d);
  };
  return (
    <section className="card" aria-label="整集概览">
      <div className="card-head">
        <h2>{ep.topics.length ? "话题段落" : "整集概览"}</h2>
        <span className="muted small">
          {ep.topics.length ? "点击跳转" : "深色刻度 = 需要你过目的改动 · 点击跳转"}
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

/** Two-track lane view of the region around the playhead, with edits marked. */
export function Lanes({
  ep,
  time,
  onSeek,
  highlight,
}: {
  ep: Episode;
  time: number;
  onSeek: (t: number) => void;
  highlight?: EditInfo | null;
}) {
  const d = ep.duration;
  const t0 = Math.max(0, Math.min(time - WINDOW / 2, d - WINDOW));
  const t1 = t0 + WINDOW;
  const x = (t: number) => `${(100 * (t - t0)) / WINDOW}%`;
  const w = (a: number, b: number) => `${(100 * Math.max(0, Math.min(b, t1) - Math.max(a, t0))) / WINDOW}%`;
  const visible = ep.edits.filter((e) => e.category !== "loudness" && e.t + e.len >= t0 && e.t <= t1);
  const click = (e: React.MouseEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    onSeek(t0 + ((e.clientX - r.left) / r.width) * WINDOW);
  };
  const ticks = [0, 1, 2, 3].map((i) => t0 + (i * WINDOW) / 3);
  return (
    <section className="card lanes" aria-label="双轨时间线">
      <div className="lane-ticks mono small muted" aria-hidden>
        {ticks.map((t) => (
          <span key={t}>{fmt(t)}</span>
        ))}
      </div>
      {ep.tracks.map((tr, i) => (
        <div className="lane" key={tr.name}>
          <span className="lane-name">{tr.name}</span>
          <div className="lane-body" onClick={click} role="presentation" data-testid={`lane-${tr.name}`}>
            {tr.clips
              .filter(([a, b]) => b >= t0 && a <= t1)
              .map(([a, b]) => (
                <div
                  key={a}
                  className={`clip clip-${i}`}
                  style={{ left: x(Math.max(a, t0)), width: w(a, b) }}
                />
              ))}
            {visible.map((e) => {
              const onThis = !e.tracks || e.tracks.includes(tr.name);
              if (!onThis) return null;
              if (e.status === "restored" || (e.tracks && e.status === "applied"))
                return (
                  <div
                    key={e.id}
                    className={`mark-span ${e.status}`}
                    style={{ left: x(Math.max(e.t, t0)), width: w(e.t, e.t + e.len) }}
                    title={e.title}
                  />
                );
              return <div key={e.id} className="mark-cut" style={{ left: x(e.t) }} title={e.title} />;
            })}
            {highlight && highlight.t + highlight.len >= t0 && highlight.t <= t1 && (
              <div
                className="mark-pending"
                style={{ left: x(Math.max(highlight.t, t0)), width: w(highlight.t, highlight.t + Math.max(highlight.len, 0.3)) }}
                title={highlight.title}
              />
            )}
          </div>
        </div>
      ))}
      <div className="lane-head-wrap" aria-hidden>
        <div className="lane-head" style={{ left: x(time) }} />
      </div>
      <p className="muted small legend">
        <span className="lg lg-cut" /> 剪切点　<span className="lg lg-lift" /> 单轨删减
        <span className="lg lg-restored" /> 已恢复　<span className="lg lg-pending" /> 待批准
      </p>
    </section>
  );
}
