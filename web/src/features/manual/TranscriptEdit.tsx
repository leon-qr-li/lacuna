import { Fragment, useEffect, useMemo, useRef } from "react";
import type { Episode } from "../../api";
import { api } from "../../api";
import { needsSpace } from "../../words";
import type { Player } from "../../usePlayer";
import { t } from "../../i18n";
import { manualApi, TEXT_S } from "./api";
import type { Line } from "./api";
import { range, useChunks } from "./chunks";
import { fmtTenths, SelBar } from "./SelBar";
import { FillerButton } from "../fillers/FillerButton";
import type { Manual } from "./useManual";

const BEFORE_S = 15; // the card shows from a little before the playhead ...
const SHOW_S = 90; // ... this far, in steps of TEXT_S so it does not jump with every word

type W = { text: string; a: number; b: number; gone: string | null; key: string };
type L = { speaker: string; start: number; words: W[] };

/** Words as text: a space only between two Latin words (lacuna_app/words.py join_words). */
const joinWords = (ws: string[]) => ws.reduce((s, w) => (s && needsSpace(s, w) ? `${s} ${w}` : s + w), "");

/** " " before `w` in its line when it and the word before it are both Latin (English), else nothing. */
const gap = (ws: W[], w: W) => {
  const i = ws.indexOf(w);
  return i > 0 && needsSpace(ws[i - 1].text, w.text) ? " " : null;
};

/** Group consecutive removed words of one edit, so a struck run is one click target. */
function pieces(words: W[]): { gone: string | null; words: W[] }[] {
  const out: { gone: string | null; words: W[] }[] = [];
  for (const w of words) {
    const last = out[out.length - 1];
    if (last && w.gone && last.gone === w.gone) last.words.push(w);
    else out.push({ gone: w.gone, words: [w] });
  }
  return out;
}

/**
 * 文字稿剪辑 (decision manual-editing): the transcript around the playhead. Click a word or drag across words to
 * select them and cut; words already cut (by the AI, the chat or by hand) stay visible struck through, a click restores them.
 */
export function TranscriptEdit({
  ep,
  time,
  player,
  m,
  run,
}: {
  ep: Episode;
  time: number;
  player: Player;
  m: Manual;
  run: (p: Promise<Episode>, msg?: string | ((next: Episode) => string)) => Promise<boolean>;
}) {
  const { sel, setSel } = m;
  const drag = useRef<{ a: W; moved: boolean; again: boolean } | null>(null);
  const box = useRef<HTMLDivElement | null>(null);
  const p0 = Math.max(0, Math.floor((time - BEFORE_S) / TEXT_S) * TEXT_S);
  const chunks = useChunks<Line[]>(
    ep.version,
    ep.has_transcript ? range(p0 / TEXT_S, Math.min(p0 / TEXT_S + SHOW_S / TEXT_S - 1, Math.floor(ep.duration / TEXT_S))) : [],
    (k) => manualApi.transcript(ep.id, ep.version, k * TEXT_S, (k + 1) * TEXT_S).then((r) => r.lines),
  );
  const lines = useMemo(() => {
    const all = [...chunks.entries()].sort((x, y) => x[0] - y[0]).flatMap(([, ls]) => ls);
    all.sort((x, y) => x.start - y.start || x.words[0][4] - y.words[0][4]);
    const out: L[] = [];
    for (const ln of all) {
      const words = ln.words.map(([text, a, b, gone, base]) => ({ text, a, b, gone, key: `${ln.speaker}:${base}` }));
      const last = out[out.length - 1];
      // a run cut in two by a chunk boundary is shown as one line again
      const lastBase = last ? Number(last.words[last.words.length - 1].key.split(":").pop()) : 0;
      if (last && last.speaker === ln.speaker && ln.words[0][4] - lastBase < 0.7) last.words.push(...words);
      else out.push({ speaker: ln.speaker, start: ln.start, words });
    }
    return out;
  }, [chunks]);
  const audible = useMemo(() => lines.flatMap((ln) => ln.words.filter((w) => !w.gone).map((w) => ({ ...w, speaker: ln.speaker }))), [lines]);
  const picked = (w: W) => !!sel && !w.gone && (w.a + w.b) / 2 >= sel.a && (w.a + w.b) / 2 < sel.b;

  const select = (a: W, b: W) => {
    const lo = Math.min(a.a, b.a);
    const hi = Math.max(a.b, b.b);
    const inside = audible.filter((w) => (w.a + w.b) / 2 >= lo && (w.a + w.b) / 2 < hi);
    setSel({ a: lo, b: hi, from: "text", speakers: [...new Set(inside.map((w) => w.speaker))], text: joinWords(inside.map((w) => w.text)) });
  };
  const wordDown = (w: W) => (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    e.preventDefault();
    // a click on the one word already selected drops the selection again
    const again = !!sel && picked(w) && audible.filter(picked).length === 1;
    drag.current = { a: w, moved: false, again };
    select(w, w);
  };
  const wordEnter = (w: W) => () => {
    const g = drag.current;
    if (!g) return;
    g.moved = true;
    select(g.a, w);
  };
  useEffect(() => {
    const end = () => {
      const g = drag.current;
      if (!g) return;
      drag.current = null;
      // a click selects that one word (so a single 嗯 or a stutter can be cut) and jumps there
      if (!g.moved) {
        if (g.again) setSel(null);
        player.seek(g.a.a);
      }
    };
    window.addEventListener("pointerup", end);
    return () => window.removeEventListener("pointerup", end);
  }, [player, setSel]);

  // keep the line being played in view (not while selecting)
  const nowLine = lines.findIndex((ln, i) => ln.start <= time && (lines[i + 1]?.start ?? Infinity) > time);
  useEffect(() => {
    if (sel || drag.current || nowLine < 0) return;
    const el = box.current?.querySelector<HTMLElement>(`[data-line="${nowLine}"]`);
    const c = box.current;
    if (el && c && (el.offsetTop < c.scrollTop || el.offsetTop + el.offsetHeight > c.scrollTop + c.clientHeight))
      c.scrollTo({ top: el.offsetTop - c.clientHeight / 3, behavior: "smooth" });
  }, [nowLine, sel]);

  const restore = (eid: string) => {
    if (ep.edits.some((x) => x.id === eid)) void run(api.review(ep.id, eid, "restore", time), t("已恢复原话，可撤销"));
  };
  const titleOf = (eid: string) => ep.edits.find((x) => x.id === eid)?.title ?? "";
  const idx = (name: string) => Math.max(0, ep.tracks.findIndex((tr) => tr.name === name)) % 6;

  return (
    <section className="card ml-tx-card" aria-label={t("文字稿剪辑")} data-testid="transcript-edit">
      <div className="card-head">
        <h2>{t("文字稿剪辑")}</h2>
        <span className="muted small">{t("选中文字 → 删掉；删过的显示删除线，点一下可恢复")}</span>
        <FillerButton ep={ep} time={time} player={player} run={run} />
      </div>
      {!ep.has_transcript ? (
        <p className="muted">{t("这一集没有文字稿，可以在上面的时间线上拖选来剪。")}</p>
      ) : (
        <div className="ml-tx" ref={box} data-testid="ml-tx">
          {lines.length === 0 && <p className="muted small">{chunks.size ? t("这一段没有人说话") : t("正在读文字稿…")}</p>}
          {lines.map((ln, i) => (
            <div key={ln.words[0].key} className={`ml-line ${i === nowLine ? "is-now" : ""}`} data-line={i}>
              <button type="button" className="ml-t mono" onClick={() => player.seek(ln.start)}>
                {fmtTenths(ln.start)}
              </button>
              <span className={`ml-who spk-${idx(ln.speaker)}`}>{ln.speaker}</span>
              <span className="ml-text">
                {pieces(ln.words).map((p) =>
                  p.gone ? (
                    <Fragment key={p.words[0].key}>
                    {gap(ln.words, p.words[0])}
                    <s
                      className="ml-gone"
                      role="button"
                      tabIndex={0}
                      title={t("{title} · 点一下恢复", { title: titleOf(p.gone) })}
                      onClick={() => restore(p.gone!)}
                      onKeyDown={(e) => e.key === "Enter" && restore(p.gone!)}
                      data-edit={p.gone}
                    >
                      {joinWords(p.words.map((w) => w.text))}
                    </s>
                    </Fragment>
                  ) : (
                    p.words.map((w) => (
                      <Fragment key={w.key}>
                      {gap(ln.words, w)}
                      <span
                        className={`ml-w ${picked(w) ? "is-sel" : ""} ${time >= w.a && time < w.b ? "is-now" : ""}`}
                        onPointerDown={wordDown(w)}
                        onPointerEnter={wordEnter(w)}
                      >
                        {w.text}
                      </span>
                      </Fragment>
                    ))
                  ),
                )}
              </span>
            </div>
          ))}
        </div>
      )}
      {sel?.from === "text" && <SelBar ep={ep} m={m} />}
    </section>
  );
}
