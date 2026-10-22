import { useEffect, useMemo, useRef, useState } from "react";
import type { AB, EditInfo, Episode, TextLine } from "../api";
import { markStep } from "../features/onboarding/api";
import { api, fmt } from "../api";
import { ABPlayer, type ABHandle } from "./ABPlayer";
import { Icon } from "./Icon";
import { t } from "../i18n";
import { Skel } from "../features/loading/Loading";
import { reviewAction } from "../features/review-keys/keys";
import { ShortcutsButton } from "../features/review-keys/Shortcuts";
import { useReviewRate } from "../features/review-speed/speed";
import { needsSpace } from "../words";
import "./ReviewView.css";

interface Props {
  ep: Episode;
  selected: string | null;
  onSelect: (e: EditInfo) => void;
  onReview: (e: EditInfo, action: "keep" | "restore" | "apply") => Promise<boolean>;
  onApproveAll: () => Promise<boolean>;
  onPauseMain: () => void;
}

const pending = (e: EditInfo) => !e.approved;

export function ReviewView({ ep, selected, onSelect, onReview, onApproveAll, onPauseMain }: Props) {
  // order comes from the server: timeline order, from the first second
  const all = useMemo(() => {
    const byId = new Map(ep.edits.map((e) => [e.id, e]));
    return ep.review.map((id) => byId.get(id)).filter((e): e is EditInfo => !!e);
  }, [ep.edits, ep.review]);
  const ranked = all;
  const done = all.length - all.filter(pending).length;
  const cur = ranked.find((e) => e.id === selected) ?? ranked.find(pending) ?? ranked[0] ?? null;
  const idx = cur ? ranked.indexOf(cur) : -1;
  const [ab, setAb] = useState<AB | null>(null);
  const [lines, setLines] = useState<TextLine[] | null>(null);
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
    if (!ok) return;
    markStep("decide");
    // 入门: 审阅 AI 第一刀 counts once three edits (or all there are) were looked at
    if (done + (pending(cur) ? 1 : 0) >= Math.min(3, all.length)) markStep("review");
    if (action === "apply") return;
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

  const routineCount = ep.routine.reduce((n, r) => n + r.count, 0);
  const routineSecs = ep.routine.reduce((n, r) => n + r.seconds, 0);
  // the heading says what the cut took away: "删掉 18 秒 · 跑题"
  const heading = (e: EditInfo) => (e.speech_s ? t("删掉 {s} 秒 · {title}", { s: e.speech_s.toFixed(e.speech_s < 10 ? 1 : 0), title: e.title }) : e.title);

  // 审阅改动, slim version A (new-user batch E1): what was cut (the struck words), how it sounds (A / B),
  // keep or restore, and 剩下的全部保留; everything else went (chips, notes, the dock, the chat box).
  return (
    <div className="review rv-slim">
      <div className="rv-top" data-testid="review-progress">
        <span className="small">
          {t("已看")} <strong>{done}</strong> / {all.length}
        </span>
        <div className="meter" aria-hidden="true">
          <span style={{ width: `${all.length ? (100 * done) / all.length : 0}%` }} />
        </div>
        <ShortcutsButton open={help} onToggle={() => setHelp((h) => !h)} />
        {leftCount > 0 && (
          <button
            type="button"
            className="btn btn-outline"
            onClick={() => void onApproveAll().then((ok) => ok && markStep("review"))}
            title={t("按 AI 现在的处理全部确认：删了的保持删，没删的保持原样。一步撤销即可退回。")}
            data-testid="review-keep-rest"
          >
            {t("剩下的全部保留（{n} 处）", { n: leftCount })}
          </button>
        )}
      </div>
      <nav className="review-nav" aria-label={t("改动列表")}>
        <ul className="rlist" ref={listRef} data-testid="review-list">
          {ranked.map((e) => (
            <li key={e.id}>
              <button
                type="button"
                data-id={e.id}
                data-category={e.category}
                className={`ritem ${e.id === cur?.id ? "is-current" : ""} ${e.approved ? (e.status === "restored" ? "is-restored" : "is-done") : ""}`}
                aria-current={e.id === cur?.id}
                onClick={() => onSelect(e)}
              >
                <span className="rdot" aria-hidden="true" />
                <span className="mono small">{fmt(e.t)}</span>
                <span className="grow">{e.title}</span>
                <span className="small rstate">
                  {e.status === "restored" ? (e.approved ? t("已恢复") : t("未应用")) : e.approved ? "✓" : ""}
                </span>
              </button>
            </li>
          ))}
        </ul>
        {routineCount > 0 && (
          <p className="muted small rv-routine" data-testid="review-routine">
            {t("另外收紧了 {n} 处停顿和口头禅，共 {s} 秒；整集试听时听到问题直接说。", { n: routineCount, s: routineSecs.toFixed(0) })}
          </p>
        )}
      </nav>

      <main className="review-main" aria-live="polite">
        {!cur ? (
          <p className="muted">{t("没有需要过目的改动。")}</p>
        ) : (
          <section className="card rv-card">
            <header className="rv-head">
              <h1 data-testid="review-title">{heading(cur)}</h1>
              <span className="grow" />
              <button type="button" className="btn btn-ghost btn-round" onClick={() => go(-1)} disabled={idx <= 0} title={t("上一处（←）")} aria-label={t("上一处")}>
                <Icon name="chevl" size={16} />
              </button>
              <span className="mono muted small">{fmt(cur.t)}</span>
              <button type="button" className="btn btn-ghost btn-round" onClick={() => go(1)} disabled={idx >= ranked.length - 1} title={t("下一处（→）")} aria-label={t("下一处")}>
                <Icon name="chev" size={16} />
              </button>
            </header>
            <p className="rv-reason">
              {cur.status === "restored" && !cur.approved && <span className="rv-k">{t("建议删，还没有应用：")}</span>}
              {cur.status === "restored" && cur.approved && <span className="rv-k">{t("已恢复原话。")}</span>}
              {cur.reason || t("（没有说明）")}
              {cur.room_tone && <span className="muted small"> {t("只抹 {who}，用底噪补上", { who: (cur.tracks ?? []).join(" / ") })}</span>}
            </p>
            {ep.has_transcript && !lines && (
              <div className="rv-lines" data-testid="lines-loading">
                <Skel w="92%" h={12} />
                <Skel w="78%" h={12} style={{ marginTop: 10 }} />
              </div>
            )}
            {lines && lines.length > 0 && (
              <div className="prose rv-lines" aria-label={t("原文对照")}>
                {lines.map((l, i) => (
                  <p key={i} className="line">
                    <span className={`spk spk-${ep.tracks.findIndex((t) => t.name === l.speaker)}`}>{l.speaker}</span>
                    {l.words.map((w, j) => (
                      <span key={j} className={w.removed ? "struck" : undefined}>
                        {j > 0 && needsSpace(l.words[j - 1].t, w.t) ? " " : ""}
                        {w.t}
                      </span>
                    ))}
                  </p>
                ))}
              </div>
            )}
            <div className="rv-act" aria-label={t("试听和决定")}>
              <ABPlayer ref={abRef} ab={ab} loading={!ab} labels={[t("A · 原话"), t("B · 剪后")]} onPlay={() => {
                  onPauseMain();
                  markStep("ab");
                }} compact rate={speed.rate} />
              <span className="grow" />
              {cur.status === "applied" ? (
                <>
                  <button type="button" className="btn btn-outline" onClick={() => void decide("restore")}>
                    {t("恢复原话")} <kbd aria-hidden="true">R</kbd>
                  </button>
                  <button type="button" className="btn btn-primary" onClick={() => void decide("keep")}>
                    <Icon name="check" /> {cur.approved ? t("已保留") : t("保留")} <kbd aria-hidden="true">K</kbd>
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
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
