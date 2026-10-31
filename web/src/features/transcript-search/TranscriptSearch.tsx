import { useEffect, useRef, useState } from "react";
import type { Episode } from "../../api";
import type { Player } from "../../usePlayer";
import { t } from "../../i18n";
import { showOnTimeline } from "../manual/EditLanes";
import { transcriptRev } from "../transcript-fix/api";
import { clearFound, searchApi, setFound, useFound } from "./api";
import "./transcript-search.css";

const WAIT_MS = 250; // after the last key before asking

/**
 * 逐字稿搜索 (Leon 2026-10-31, direction A, kept small): a pill on 逐字稿剪辑 like the chips beside it. Type and
 * every place lights up in the transcript and as ticks on the ruler; Enter / ↓ jumps to the next one after the
 * playhead, Shift+Enter / ↑ back, Esc clears; Ctrl+F (⌘F) in 整集试听 puts the cursor in it. A jump moves the
 * playhead and keeps playing or paused as it was; cut words are found too and shown struck through.
 */
export function TranscriptSearch({ ep, time, player }: { ep: Episode; time: number; player: Player }) {
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement | null>(null);
  const found = useFound();
  const key = `${ep.version}|${transcriptRev(ep)}`;

  useEffect(() => {
    const text = q.trim();
    if (!text) {
      clearFound();
      setBusy(false);
      return;
    }
    let live = true;
    setBusy(true);
    const h = window.setTimeout(() => {
      searchApi.find(ep.id, ep.version, text).then(
        (r) => {
          if (!live) return;
          setBusy(false);
          // after a cut the times move: stay on the same place (by order) if it is still there
          const before = found.q === text ? found.cur : -1;
          setFound({ q: text, hits: r.hits, cur: before < r.hits.length ? before : -1 });
        },
        () => live && setBusy(false),
      );
    }, WAIT_MS);
    return () => {
      live = false;
      window.clearTimeout(h);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, ep.id, key]);
  useEffect(() => clearFound, [ep.id]);

  // Ctrl+F / ⌘F while 整集试听 is on screen (the workspace stays mounted, hidden, in 改动审阅)
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      const el = input.current;
      if (!el || !el.offsetParent || !(e.ctrlKey || e.metaKey) || e.altKey || e.key.toLowerCase() !== "f") return;
      e.preventDefault();
      el.focus();
      el.select();
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, []);

  const live = found.q === q.trim() && !!found.q;
  const hits = live ? found.hits : [];
  const go = (step: 1 | -1) => {
    if (!hits.length) return;
    let i: number;
    if (found.cur >= 0) i = (found.cur + step + hits.length) % hits.length;
    else if (step > 0) i = Math.max(0, hits.findIndex((h) => h.start >= time - 0.05));
    else {
      const before = hits.map((h) => h.start < time - 0.05).lastIndexOf(true);
      i = before >= 0 ? before : hits.length - 1;
    }
    setFound({ ...found, cur: i });
    player.seek(hits[i].start);
    showOnTimeline(hits[i].start, hits[i].end);
  };
  const clear = () => {
    setQ("");
    input.current?.focus();
  };

  const count = !q.trim() ? null : busy && !live ? "…" : !hits.length ? t("无结果") : found.cur >= 0 ? `${found.cur + 1}/${hits.length}` : t("{n} 处", { n: hits.length });
  return (
    <span className={`ts ${q ? "has-q" : ""}`} role="search" data-testid="ts">
      <svg className="ts-ico" viewBox="0 0 16 16" aria-hidden="true">
        <circle cx="7" cy="7" r="4.6" />
        <path d="m10.6 10.6 3.4 3.4" />
      </svg>
      <input
        ref={input}
        type="search"
        className="ts-in"
        value={q}
        maxLength={60}
        placeholder={t("搜索逐字稿")}
        aria-label={t("搜索逐字稿（Ctrl+F）")}
        onChange={(e) => setQ(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            go(e.shiftKey ? -1 : 1);
          } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
            e.preventDefault();
            go(e.key === "ArrowDown" ? 1 : -1);
          } else if (e.key === "Escape") {
            e.preventDefault();
            if (q) setQ("");
            else input.current?.blur();
          }
        }}
        data-testid="ts-in"
      />
      {count && (
        <>
          <span className={`ts-n mono ${live && !hits.length ? "is-none" : ""}`} aria-live="polite" data-testid="ts-n">
            {count}
          </span>
          <button type="button" className="ts-b" onClick={() => go(-1)} disabled={!hits.length} aria-label={t("上一处（Shift+回车）")} title={t("上一处（Shift+回车）")} data-testid="ts-prev">
            <svg viewBox="0 0 16 16" aria-hidden="true"><path d="m4 10 4-4 4 4" /></svg>
          </button>
          <button type="button" className="ts-b" onClick={() => go(1)} disabled={!hits.length} aria-label={t("下一处（回车）")} title={t("下一处（回车）")} data-testid="ts-next">
            <svg viewBox="0 0 16 16" aria-hidden="true"><path d="m4 6 4 4 4-4" /></svg>
          </button>
          <button type="button" className="ts-b" onClick={clear} aria-label={t("清除搜索")} title={t("清除搜索")} data-testid="ts-clear">
            <svg viewBox="0 0 16 16" aria-hidden="true"><path d="m5 5 6 6M11 5l-6 6" /></svg>
          </button>
        </>
      )}
    </span>
  );
}

/** Where the text is said, as ticks on the timeline ruler (the one jumped to stands out); a click jumps there. */
export function SearchTicks({ t0, span, player }: { t0: number; span: number; player: Player }) {
  const found = useFound();
  if (!found.hits.length) return null;
  return (
    <>
      {found.hits.map((h, i) =>
        h.start < t0 || h.start > t0 + span ? null : (
          <button
            type="button"
            key={`${h.start}-${i}`}
            className={`ts-tick ${i === found.cur ? "is-cur" : ""} ${h.gone ? "is-gone" : ""}`}
            style={{ left: `${(100 * (h.start - t0)) / span}%` }}
            onPointerDown={(e) => e.stopPropagation()}
            onClick={() => {
              setFound({ ...found, cur: i });
              player.seek(h.start);
            }}
            aria-label={t("跳到第 {n} 处", { n: i + 1 })}
            data-testid="ts-tick"
          />
        ),
      )}
    </>
  );
}
