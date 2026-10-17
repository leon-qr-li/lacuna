import { useEffect, useMemo, useRef, useState } from "react";
import type { AB, EditInfo, Episode, TextLine } from "../api";
import { api, confidenceLabel, fmt, statusLabel } from "../api";
import { ABPlayer, type ABHandle } from "./ABPlayer";

interface Props {
  ep: Episode;
  selected: string | null;
  onSelect: (e: EditInfo) => void;
  onReview: (e: EditInfo, action: "keep" | "restore" | "apply") => Promise<boolean>;
  onApproveAll: () => Promise<boolean>;
  onPauseMain: () => void;
}

const LATIN = /^[A-Za-z0-9']+$/;

const pending = (e: EditInfo) => !e.approved;

export function ReviewView({ ep, selected, onSelect, onReview, onApproveAll, onPauseMain }: Props) {
  // order comes from the server: timeline order, from the first second
  const all = useMemo(() => {
    const byId = new Map(ep.edits.map((e) => [e.id, e]));
    return ep.review.map((id) => byId.get(id)).filter((e): e is EditInfo => !!e);
  }, [ep.edits, ep.review]);
  const [onlyPending, setOnlyPending] = useState(false);
  // the current edit stays listed even once reviewed, so the view never jumps under Leon's cursor
  const ranked = onlyPending ? all.filter((e) => pending(e) || e.id === selected) : all;
  const done = all.length - all.filter(pending).length;
  const cur = ranked.find((e) => e.id === selected) ?? ranked.find(pending) ?? ranked[0] ?? null;
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

  const select = (n: EditInfo | undefined) => {
    if (!n) return;
    onSelect(n);
    listRef.current?.querySelector<HTMLElement>(`[data-id="${n.id}"]`)?.scrollIntoView({ block: "nearest" });
  };
  const go = (d: number) => select(ranked[Math.max(0, Math.min(ranked.length - 1, idx + d))]);

  // decide on the current edit, then move on to the next one still waiting (wrapping round to earlier skips)
  const decide = async (action: "keep" | "restore" | "apply") => {
    if (!cur) return;
    const ok = await onReview(cur, action);
    if (!ok || action === "apply") return;
    const rest = [...ranked.slice(idx + 1), ...ranked.slice(0, Math.max(idx, 0))];
    select(rest.find((e) => pending(e) && e.id !== cur.id));
  };
  const leftCount = all.length - done;

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
      else if (k === "y" && cur) void decide(cur.status === "applied" ? "keep" : "restore");
      else if (k === "r" && cur && cur.status === "applied") void decide("restore");
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
          <h2>需要你过目 · {all.length}</h2>
          <p className="muted small">按时间先后排，从第一秒开始。已经应用在第一刀里，你只需要决定是否恢复。</p>
          <div className="batch" data-testid="review-progress">
            <div className="row baseline gap8">
              <span className="small">
                已过目 <strong>{done}</strong> / {all.length}
              </span>
              <label className="small muted row gap4">
                <input type="checkbox" checked={onlyPending} onChange={(e) => setOnlyPending(e.target.checked)} />
                只看没过目的
              </label>
            </div>
            <div className="meter" aria-hidden="true">
              <span style={{ width: `${all.length ? (100 * done) / all.length : 0}%` }} />
            </div>
            {leftCount > 0 && (
              <button
                type="button"
                className="btn btn-outline btn-block"
                onClick={() => void onApproveAll()}
                title="按 AI 现在的处理全部确认：删了的保持删，没删的保持原样。一步撤销即可退回。"
              >
                剩下 {leftCount} 处全部通过
              </button>
            )}
          </div>
          <ul className="rlist" ref={listRef} data-testid="review-list">
            {ranked.map((e) => (
              <li key={e.id}>
                <button
                  type="button"
                  data-id={e.id}
                  data-category={e.category}
                  className={`ritem ${e.id === cur?.id ? "is-current" : ""}`}
                  aria-current={e.id === cur?.id}
                  onClick={() => onSelect(e)}
                >
                  <span className="mono small">{fmt(e.t)}</span>
                  <span className="grow">{e.title}</span>
                  {e.category === "content" && <span className="small rtag">内容</span>}
                  <span className="small rstate">
                    {e.status === "restored" ? (e.approved ? "不删 ✓" : "未应用") : e.approved ? "✓" : ""}
                  </span>
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
              <h2 className="sub">为什么{cur.status === "restored" ? (cur.approved ? "删过（现已恢复）" : "建议删（还没有应用）") : "删"}</h2>
              <p>{cur.reason || "（没有说明）"}</p>
              <p className="muted small">
                把握度：{confidenceLabel(cur.confidence)} · 类型：{cur.category_label}
                {cur.speech_s ? ` · 删掉说话 ${cur.speech_s.toFixed(1)} 秒` : ""} · {statusLabel(cur)} · 可随时恢复
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
                  <button type="button" className="btn btn-primary" onClick={() => void decide("keep")}>
                    {cur.approved ? "✓ 已保留" : "保留这个删除"}
                  </button>
                  <button type="button" className="btn btn-outline" onClick={() => void decide("restore")}>
                    恢复原话
                  </button>
                </>
              ) : (
                <>
                  {!cur.approved && (
                    <button type="button" className="btn btn-primary" onClick={() => void decide("restore")}>
                      不删，保持原话
                    </button>
                  )}
                  <button type="button" className={`btn ${cur.approved ? "btn-primary" : "btn-outline"}`} onClick={() => void decide("apply")}>
                    重新应用这个删除
                  </button>
                </>
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
            <p className="muted small">快捷键：J / K 上一条下一条，空格播放，A / B 切换原始与剪后，Y 通过（保持现状）并跳到下一条，R 恢复原话并跳到下一条。</p>
          </>
        )}
      </main>
    </div>
  );
}
