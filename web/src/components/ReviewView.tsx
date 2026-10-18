import { useEffect, useMemo, useRef, useState } from "react";
import type { AB, EditInfo, Episode, TextLine } from "../api";
import { api, confidenceLabel, fmt, statusLabel } from "../api";
import { ABPlayer, type ABHandle } from "./ABPlayer";
import { GrowText } from "./GrowText";
import { Icon } from "./Icon";
import { t } from "../i18n";
import { Skel, Waiting } from "../features/loading/Loading";
import { reviewAction } from "../features/review-keys/keys";
import { DockProgress, ShortcutsButton } from "../features/review-keys/Shortcuts";
import { SpeedButton } from "../features/review-speed/SpeedButton";
import { useReviewRate } from "../features/review-speed/speed";

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
  const [tweaking, setTweaking] = useState(false);
  const [help, setHelp] = useState(false);
  const abRef = useRef<ABHandle>(null);
  const speed = useReviewRate();
  const listRef = useRef<HTMLUListElement>(null);

  // load A/B renders + original words whenever the selected edit (or its state) changes
  const curKey = cur ? `${cur.id}:${cur.status}:${ep.version}` : "";
  useEffect(() => {
    if (!cur) return;
    let live = true;
    setAb(null);
    setReply(null);
    setLines(null);
    api.editAB(ep.id, cur.id).then((r) => live && setAb(r)).catch(() => undefined);
    if (ep.has_transcript)
      api.editText(ep.id, cur.id).then((r) => live && setLines(r.lines)).catch(() => live && setLines([]));
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
      const a = reviewAction(e);
      if (!a) return;
      if (a === "prev") go(-1);
      else if (a === "next") go(1);
      else if (a === "toggle") {
        e.preventDefault();
        abRef.current?.toggle();
      } else if (a === "a") abRef.current?.select("before");
      else if (a === "b") abRef.current?.select("after");
      else if (a === "keep" && cur) void decide(cur.status === "applied" ? "keep" : "restore");
      else if (a === "restore" && cur && cur.status === "applied") void decide("restore");
      else if (a === "speed") speed.cycle();
      else if (a === "help") setHelp((h) => !h);
      else return;
      if (a === "prev" || a === "next") e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const sendTweak = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!cur || !tweak.trim() || tweaking) return;
    setTweaking(true);
    try {
      const r = await api.chat(ep.id, tweak.trim(), cur.t);
      setReply(r.reply + (r.proposal ? t("（建议已放到「整集试听」的对话里，试听后批准）") : ""));
      setTweak("");
    } catch (err) {
      setReply(t("操作失败：{message}", { message: (err as Error).message }));
    } finally {
      setTweaking(false);
    }
  };

  return (
    <div className="review">
      <nav className="review-nav" aria-label={t("改动列表")}>
        <section>
          <h2>{t("需要你过目 · {n}", { n: all.length })}</h2>
          <p className="muted small">{t("按时间先后排，从第一秒开始。已经应用在第一刀里，你只需要决定是否恢复。")}</p>
          <div className="batch" data-testid="review-progress">
            <div className="row baseline gap8">
              <span className="small">
                {t("已过目")} <strong>{done}</strong> / {all.length}
              </span>
              <label className="small muted row gap4">
                <input type="checkbox" checked={onlyPending} onChange={(e) => setOnlyPending(e.target.checked)} />
                {t("只看没过目的")}
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
                title={t("按 AI 现在的处理全部确认：删了的保持删，没删的保持原样。一步撤销即可退回。")}
              >
                {t("剩下 {n} 处全部通过", { n: leftCount })}
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
                  {e.category === "content" && <span className="small rtag">{t("内容")}</span>}
                  <span className="small rstate">
                    {e.status === "restored" ? (e.approved ? t("不删 ✓") : t("未应用")) : e.approved ? "✓" : ""}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
        <section>
          <h2>{t("常规清理 · {n} 处", { n: ep.routine.reduce((n, r) => n + r.count, 0) })}</h2>
          <p className="muted small">{t("按类别汇总，不逐条审批。整集试听时听到问题直接说即可。")}</p>
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
          <p className="muted">{t("没有需要过目的改动。")}</p>
        ) : (
          <>
            <header className="rv-head">
              <span className={`chip ${pending(cur) ? "chip-warn" : "chip-ok"}`}>
                {t("第 {i} / {n} 处", { i: idx + 1, n: ranked.length })}{pending(cur) ? "" : t(" · 已过目")}
              </span>
              <h1 data-testid="review-title">{cur.title}</h1>
              <span className="mono muted small">
                {t("成品 {time}", { time: fmt(cur.t) })}
                {cur.raw && t(" · 原始 {p0}{p1}–{p2}", { p0: cur.tracks ? cur.tracks.join("/") + " " : "", p1: fmt(cur.raw[0]), p2: fmt(cur.raw[1]) })}
              </span>
            </header>
            <section className="card rv-why">
              <span className="rv-k">
                {cur.status === "restored" ? (cur.approved ? t("为什么删过（现已恢复）") : t("为什么建议删（还没有应用）")) : t("为什么删")}
              </span>
              <div>
                <p>{cur.reason || t("（没有说明）")}</p>
                <div className="rv-chips small">
                  <span className="chip chip-plain">{t("把握度")} {confidenceLabel(cur.confidence)}</span>
                  <span className="chip chip-plain">{cur.category_label}</span>
                  {cur.speech_s ? <span className="chip chip-plain">{t("删掉说话 {s} 秒", { s: cur.speech_s.toFixed(1) })}</span> : null}
                  <span className="chip chip-plain">{statusLabel(cur)}</span>
                  {cur.room_tone && <span className="chip chip-plain">{t("只抹 {who}，用底噪补上", { who: (cur.tracks ?? []).join(" / ") })}</span>}
                  <span className="chip chip-ok">{t("可随时恢复")}</span>
                </div>
              </div>
            </section>
            {ep.has_transcript && !lines && (
              <section className="card rv-lines" aria-label={t("原文对照")} data-testid="lines-loading">
                <Skel w="22%" h={12} />
                <Skel w="92%" h={12} style={{ marginTop: 14 }} />
                <Skel w="78%" h={12} style={{ marginTop: 10 }} />
              </section>
            )}
            {lines && lines.length > 0 && (
              <section className="card prose rv-lines" aria-label={t("原文对照")}>
                <div className="card-head">
                  <h2 className="sub">{t("原话")}</h2>
                  <span className="muted small">{t("只显示，不改写；划线部分被剪掉")}</span>
                </div>
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
            <form className="rv-tweak" onSubmit={sendTweak}>
              <Icon name="chat" />
              <label htmlFor="tweak" className="sr-only">
                {t("用一句话调整")}
              </label>
              <GrowText
                id="tweak"
                value={tweak}
                onChange={setTweak}
                placeholder={t("或者直接说：恢复这处 / 停顿短一点")}
              />
            </form>
            {tweaking && <Waiting label={t("Claude 正在看这附近的逐字稿…")} />}
            {reply && !tweaking && <p className="note">{reply}</p>}
            <p className="muted small">{t("快捷键：空格播放，← / → 上一处下一处，K 保留，R 恢复原话，A / B 切换原始与剪后，S 倍速，? 看全部。")}</p>

            {/* the floating dock: listen, compare, decide; everything for this edit in one place */}
            <section className="dock rv-dock" aria-label={t("试听和决定")}>
              <button type="button" className="btn btn-ghost btn-round" onClick={() => go(-1)} disabled={idx <= 0} title={t("上一处（←）")} aria-label={t("上一处")}>
                <Icon name="chevl" size={18} />
              </button>
              <ABPlayer ref={abRef} ab={ab} loading={!ab} labels={[t("A · 原始"), t("B · 剪后")]} onPlay={onPauseMain} compact rate={speed.rate} />
              <SpeedButton rate={speed.rate} onChange={speed.setRate} />
              <span className="grow" />
              <DockProgress done={done} total={all.length} />
              <ShortcutsButton open={help} onToggle={() => setHelp((h) => !h)} />
              {cur.status === "applied" ? (
                <>
                  <button type="button" className="btn btn-outline" onClick={() => void decide("restore")}>
                    {t("恢复原话")} <kbd aria-hidden="true">R</kbd>
                  </button>
                  <button type="button" className="btn btn-primary" onClick={() => void decide("keep")}>
                    <Icon name="check" /> {cur.approved ? t("已保留") : t("保留这个删除")} <kbd aria-hidden="true">K</kbd>
                  </button>
                </>
              ) : (
                <>
                  <button type="button" className={`btn ${cur.approved ? "btn-primary" : "btn-outline"}`} onClick={() => void decide("apply")}>
                    {t("重新应用这个删除")}
                  </button>
                  {!cur.approved && (
                    <button type="button" className="btn btn-primary" onClick={() => void decide("restore")}>
                      <Icon name="check" /> {t("不删，保持原话")} <kbd aria-hidden="true">K</kbd>
                    </button>
                  )}
                </>
              )}
              <button
                type="button"
                className="btn btn-ghost btn-round"
                onClick={() => go(1)}
                disabled={idx >= ranked.length - 1}
                title={t("下一处（→）")}
                aria-label={t("下一处")}
              >
                <Icon name="chev" size={18} />
              </button>
            </section>
          </>
        )}
      </main>
    </div>
  );
}
