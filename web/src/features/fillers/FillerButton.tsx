import { useEffect, useRef, useState } from "react";
import type { Episode } from "../../api";
import type { Player } from "../../usePlayer";
import { t } from "../../i18n";
import { fillersApi } from "./api";
import type { Fillers } from "./api";
import "./fillers.css";

/**
 * 去掉 um / uh (decision english-fillers): a chip on 文字稿剪辑 of an English episode with how many um / uh are
 * still heard; it opens a small panel to hear them one by one and take them all out (or one host's) in one
 * undoable step. Each one cut stays in the transcript struck through, a click there brings back just that one.
 */
export function FillerButton({
  ep,
  time,
  player,
  run,
}: {
  ep: Episode;
  time: number;
  player: Player;
  run: (p: Promise<Episode>, msg?: string | ((next: Episode) => string)) => Promise<boolean>;
}) {
  const [data, setData] = useState<Fillers | null>(null);
  const [open, setOpen] = useState(false);
  const [off, setOff] = useState<Set<string>>(new Set()); // hosts left out
  const [busy, setBusy] = useState(false);
  const box = useRef<HTMLSpanElement | null>(null);

  useEffect(() => {
    let live = true;
    fillersApi
      .list(ep.id)
      .then((d) => live && setData(d))
      .catch(() => live && setData(null));
    return () => {
      live = false;
    };
  }, [ep.id, ep.version]);

  // a click outside or Esc closes the panel
  useEffect(() => {
    if (!open) return;
    const click = (e: PointerEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    const key = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("pointerdown", click);
    window.addEventListener("keydown", key);
    return () => {
      window.removeEventListener("pointerdown", click);
      window.removeEventListener("keydown", key);
    };
  }, [open]);

  if (!data || data.language !== "en" || data.items.length === 0) return null;
  const hosts = data.hosts;
  const picked = hosts.filter((h) => !off.has(h.name));
  const n = picked.reduce((s, h) => s + h.left, 0);
  const left = data.items.filter((f) => !f.gone);
  const next = left.find((f) => f.t > time + 0.3) ?? left[0];
  const hear = () => {
    if (!next) return;
    player.seek(Math.max(0, next.t - 1.5));
    player.play();
  };
  const cut = async () => {
    setBusy(true);
    const all = picked.length === hosts.length;
    const ok = await run(fillersApi.cut(ep.id, all ? null : picked.map((h) => h.name), time), (r) =>
      t("已去掉 {n} 个 um / uh，可撤销", { n: (r as Episode & { cut: number }).cut }),
    );
    setBusy(false);
    if (ok) setOpen(false);
  };
  const toggle = (name: string) =>
    setOff((s) => {
      const x = new Set(s);
      if (x.has(name)) x.delete(name);
      else x.add(name);
      return x;
    });

  return (
    <span className="fl" ref={box}>
      <button
        type="button"
        className={`fl-chip ${data.left ? "" : "is-clean"}`}
        aria-expanded={open}
        onClick={() => {
          if (!open) setOff(new Set()); // every host ticked each time it opens
          setOpen(!open);
        }}
        data-testid="fillers-btn"
        title={t("这一集的 um / uh")}
      >
        um / uh <b>{data.left}</b>
      </button>
      {open && (
        <div className="fl-pop" role="dialog" aria-label={t("去掉 um / uh")} data-testid="fillers-pop">
          <div className="fl-head">
            <strong>{t("去掉 um / uh")}</strong>
            <span className="muted small">
              {data.left ? t("还听得到 {n} 个，已剪掉 {m} 个", { n: data.left, m: data.cut }) : t("都剪掉了（{m} 个）", { m: data.cut })}
            </span>
          </div>
          {data.left > 0 && (
            <>
              <ul className="fl-hosts">
                {hosts.map((h, i) => (
                  <li key={h.name}>
                    <label>
                      <input type="checkbox" checked={!off.has(h.name)} disabled={!h.left} onChange={() => toggle(h.name)} />
                      <span className={`fl-who spk-${i % 6}`}>{h.name}</span>
                      <span className="grow" />
                      <span className="muted small">{t("{n} 个", { n: h.left })}</span>
                    </label>
                  </li>
                ))}
              </ul>
              <div className="fl-actions">
                <button type="button" className="btn btn-ghost btn-small" onClick={hear} data-testid="fillers-hear">
                  {t("听下一个")}
                </button>
                <span className="grow" />
                <button type="button" className="btn btn-primary btn-small" disabled={busy || n === 0} onClick={() => void cut()} data-testid="fillers-cut">
                  {t("去掉 {n} 个", { n })}
                </button>
              </div>
              <p className="muted small fl-note">{t("剪掉的在文字稿里显示删除线，点一下单独恢复；也可以一步撤销。")}</p>
            </>
          )}
        </div>
      )}
    </span>
  );
}
