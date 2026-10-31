import { useEffect, useRef, useState } from "react";
import type { Episode } from "../../api";
import type { Player } from "../../usePlayer";
import { t } from "../../i18n";
import { fmtTenths } from "../manual/SelBar";
import { nameCheckApi, type NameFix } from "./api";
import "./name-check.css";

/**
 * 专有名词核对 at import (lacuna_app/name_check.py): a chip on 逐字稿剪辑 saying how many names the import fixed;
 * it opens a list (heard → written, what it is, where) with 「改回原样」 for each, which puts the heard text back
 * and remembers to leave it alone next time.
 */
export function NameCheck({
  ep,
  time,
  player,
  run,
}: {
  ep: Episode;
  time: number;
  player: Player;
  run: (p: Promise<Episode>, msg?: string | ((next: Episode) => string), opts?: { undo?: boolean }) => Promise<boolean>;
}) {
  const [rows, setRows] = useState<NameFix[] | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const box = useRef<HTMLSpanElement | null>(null);

  useEffect(() => {
    let live = true;
    nameCheckApi
      .list(ep.id)
      .then((d) => live && setRows(d.rows))
      .catch(() => live && setRows(null));
    return () => {
      live = false;
    };
  }, [ep.id]);

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

  if (!rows?.length) return null;
  const applied = rows.filter((r) => r.state === "applied");
  const keep = async (f: NameFix) => {
    setBusy(f.wrong + f.right);
    const p = nameCheckApi.keep(ep.id, f, time);
    await run(
      p.then((r) => {
        setRows(r.names);
        return r;
      }),
      t("已改回「{wrong}」，以后也不再改", { wrong: f.wrong }),
    );
    setBusy(null);
  };
  return (
    <span className="nc" ref={box}>
      <button type="button" className="nc-chip" aria-expanded={open} onClick={() => setOpen(!open)} data-testid="name-check-btn"
        title={t("导入时 LACUNA 核对并改好的片名、人名")}>
        {t("专有名词已核对")} <b>{applied.length}</b>
      </button>
      {open && (
        <div className="nc-pop" role="dialog" aria-label={t("导入时改好的专有名词")} data-testid="name-check-pop">
          <div className="nc-head">
            <strong>{t("导入时改好的专有名词")}</strong>
            <span className="muted small">{t("逐字稿里听错的名字已经改好，只改了文字，音频和剪辑没动。哪个改错了，点「改回原样」。")}</span>
          </div>
          <ul className="nc-list">
            {rows.map((r) => (
              <li key={r.wrong + r.right} className={r.state === "kept" ? "is-kept" : ""} data-testid="name-check-row">
                <div className="nc-pair">
                  <span className="nc-wrong">{r.wrong}</span>
                  <span aria-hidden="true">→</span>
                  <strong>{r.right}</strong>
                  <span className="muted small">{t("共 {n} 处", { n: r.count })}</span>
                </div>
                {r.why && <div className="muted small nc-why">{r.why}</div>}
                <div className="nc-actions">
                  {r.places[0] && (
                    <button type="button" className="btn btn-ghost btn-small" onClick={() => player.seek(r.places.find((p) => p.start > time + 0.5)?.start ?? r.places[0].start)}>
                      {t("听一下（{time}）", { time: fmtTenths((r.places.find((p) => p.start > time + 0.5) ?? r.places[0]).start) })}
                    </button>
                  )}
                  <span className="grow" />
                  {r.state === "applied" ? (
                    <button type="button" className="btn btn-outline btn-small" disabled={busy !== null} onClick={() => void keep(r)} data-testid="name-check-keep">
                      {t("改回原样")}
                    </button>
                  ) : (
                    <span className="chip">{t("已改回")}</span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </span>
  );
}
