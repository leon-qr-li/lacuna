import { useEffect, useMemo, useRef, useState } from "react";
import type { AB, EditInfo, Episode, TextLine } from "../api";
import { api, confidenceLabel, fmt, statusLabel } from "../api";
import { ABPlayer, type ABHandle } from "./ABPlayer";

interface Props {
  ep: Episode;
  selected: string | null;
  onSelect: (e: EditInfo) => void;
  onReview: (e: EditInfo, action: "keep" | "restore" | "apply") => Promise<void>;
  onPauseMain: () => void;
}

/** Impact ranking: long removals the AI is less sure about first. */
const LATIN = /^[A-Za-z0-9']+$/;

const impact = (e: EditInfo) => e.len * (1.3 - e.confidence);

export function ReviewView({ ep, selected, onSelect, onReview, onPauseMain }: Props) {
  const ranked = useMemo(
    () => ep.edits.filter((e) => e.consequential).sort((a, b) => impact(b) - impact(a)),
    [ep.edits],
  );
  const cur = ranked.find((e) => e.id === selected) ?? ranked[0] ?? null;
  const idx = cur ? ranked.indexOf(cur) : -1;
  const [ab, setAb] = useState<AB | null>(null);
  const [lines, setLines] = useState<TextLine[] | null>(null);
  const [tweak, setTweak] = useState("");
  const [reply, setReply] = useState<string | null>(null);
  const abRef = useRef<ABHandle>(null);
  const listRef = useRef<HTMLUListElement>(null);

  // load A/B renders + original words whenever the selected edit (or its state) changes
  const curKey = cur ? `${cur.id}:${cur.status}:${ep.version}` : "";
  useEffect(() => {
    if (!cur) return;
    let live = true;
    setAb(null);
    setReply(null);
    api.editAB(ep.id, cur.id).then((r) => live && setAb(r)).catch(() => undefined);
    if (ep.has_transcript)
      api.editText(ep.id, cur.id).then((r) => live && setLines(r.lines)).catch(() => setLines(null));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [curKey]);

  useEffect(() => {
    if (cur && cur.id !== selected) onSelect(cur);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cur?.id]);

  const go = (d: number) => {
    const n = ranked[Math.max(0, Math.min(ranked.length - 1, idx + d))];
    if (n) {
      onSelect(n);
      listRef.current?.querySelector<HTMLElement>(`[data-id="${n.id}"]`)?.scrollIntoView({ block: "nearest" });
    }
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || e.metaKey || e.ctrlKey || e.altKey) return;
      const k = e.key.toLowerCase();
      if (k === "j") go(-1);
      else if (k === "k") go(1);
      else if (k === " ") {
        e.preventDefault();
        abRef.current?.toggle();
      } else if (k === "a") abRef.current?.select("before");
      else if (k === "b") abRef.current?.select("after");
      else if (k === "r" && cur && cur.status === "applied") void onReview(cur, "restore");
      else return;
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const sendTweak = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!cur || !tweak.trim()) return;
    const r = await api.chat(ep.id, tweak.trim(), cur.t);
    setReply(r.reply + (r.proposal ? "（建议已放到「整集试听」的对话里，试听后批准）" : ""));
    setTweak("");
  };

  return (
    <div className="review">
      <nav className="review-nav" aria-label="改动列表">
        <section>
          <h2>需要你过目 · {ranked.length}</h2>
          <p className="muted small">按影响大小排序。已经应用在第一刀里，你只需要决定是否恢复。</p>
          <ul className="rlist" ref={listRef} data-testid="review-list">
            {ranked.map((e) => (
              <li key={e.id}>
                <button
                  type="button"
                  data-id={e.id}
                  className={`ritem ${e.id === cur?.id ? "is-current" : ""}`}
                  aria-current={e.id === cur?.id}
                  onClick={() => onSelect(e)}
                >
                  <span className="mono small">{fmt(e.t)}</span>
                  <span className="grow">{e.title}</span>
                  <span className="small rstate">{e.status === "restored" ? "已恢复" : e.approved ? "✓" : ""}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
        <section>
          <h2>常规清理 · {ep.routine.reduce((n, r) => n + r.count, 0)} 处</h2>
          <p className="muted small">按类别汇总，不逐条审批。整集试听时听到问题直接说即可。</p>
          <ul className="routine">
            {ep.routine.map((r) => (
              <li key={r.category}>
                <span>{r.label}</span>
                <span className="mono">
                  {r.count}
                  {r.seconds > 0 && <span className="muted small"> · {r.seconds.toFixed(0)}s</span>}
                </span>
              </li>
            ))}
          </ul>
        </section>
      </nav>

      <main className="review-main" aria-live="polite">
        {!cur ? (
          <p className="muted">没有需要过目的改动。</p>
        ) : (
          <>
            <div className="row wrap baseline gap12">
              <h1 data-testid="review-title">{cur.title}</h1>
              <span className="mono muted">
                成品 {fmt(cur.t)}
                {cur.raw && ` · 原始 ${cur.tracks ? cur.tracks.join("/") + " " : ""}${fmt(cur.raw[0])}–${fmt(cur.raw[1])}`}
              </span>
            </div>
            <section className="card prose">
              <h2 className="sub">为什么{cur.status === "restored" ? "删过（现已恢复）" : "删"}</h2>
              <p>{cur.reason || "（没有说明）"}</p>
              <p className="muted small">
                把握度：{confidenceLabel(cur.confidence)} · 类型：{cur.category_label} · {statusLabel(cur)} · 可随时恢复
              </p>
            </section>
            {lines && lines.length > 0 && (
              <section className="card prose" aria-label="原文对照">
                <h2 className="sub">原话（只显示，不改写；划线部分被剪掉）</h2>
                {lines.map((l, i) => (
                  <p key={i} className="line">
                    <span className={`spk spk-${ep.tracks.findIndex((t) => t.name === l.speaker)}`}>{l.speaker}</span>
                    {l.words.map((w, j) => (
                      <span key={j} className={w.removed ? "struck" : undefined}>
                        {j > 0 && LATIN.test(w.t) && LATIN.test(l.words[j - 1].t) ? " " : ""}
                        {w.t}
                      </span>
                    ))}
                  </p>
                ))}
              </section>
            )}
            <section className="dark-bar" aria-label="试听">
              <ABPlayer ref={abRef} ab={ab} loading={!ab} labels={["原始（前后 10 秒）", "剪后（前后 10 秒）"]} onPlay={onPauseMain} dark />
            </section>
            <div className="row wrap gap10">
              {cur.status === "applied" ? (
                <>
                  <button type="button" className="btn btn-primary" onClick={() => onReview(cur, "keep")}>
                    {cur.approved ? "✓ 已保留" : "保留这个删除"}
                  </button>
                  <button type="button" className="btn btn-outline" onClick={() => onReview(cur, "restore")}>
                    恢复原话
                  </button>
                </>
              ) : (
                <button type="button" className="btn btn-primary" onClick={() => onReview(cur, "apply")}>
                  重新应用这个删除
                </button>
              )}
              <form className="grow row gap8" onSubmit={sendTweak}>
                <label htmlFor="tweak" className="sr-only">
                  用一句话调整
                </label>
                <input
                  id="tweak"
                  type="text"
                  value={tweak}
                  onChange={(e) => setTweak(e.target.value)}
                  placeholder="或者直接说：恢复这处 / 停顿短一点"
                />
              </form>
            </div>
            {reply && <p className="note">{reply}</p>}
            <p className="muted small">快捷键：J / K 上一条下一条，空格播放，A / B 切换原始与剪后，R 恢复。</p>
          </>
        )}
      </main>
    </div>
  );
}
