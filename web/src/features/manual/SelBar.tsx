import type { Episode } from "../../api";
import { t } from "../../i18n";
import type { Manual } from "./useManual";

/** m:ss.s - a selection needs tenths */
export const fmtTenths = (s: number) => {
  const m = Math.floor(s / 60);
  const r = s - m * 60;
  return `${m}:${r.toFixed(1).padStart(4, "0")}`;
};

/** What to do with the selection: cut it from every track, silence one host, play it, drop it. */
export function SelBar({ ep, m }: { ep: Episode; m: Manual }) {
  const { sel, busy } = m;
  if (!sel) return null;
  const hosts = sel.speakers?.length ? ep.tracks.filter((tr) => sel.speakers!.includes(tr.name)) : ep.tracks;
  const quote = sel.text ? `「${sel.text.length > 16 ? sel.text.slice(0, 16) + "…" : sel.text}」` : "";
  return (
    <div className="ml-bar" role="toolbar" aria-label={t("选中的这一段")} data-testid="ml-bar">
      <span className="ml-what" title={sel.text ?? ""}>
        {t("已选")} {sel.speakers?.length === 1 ? `${sel.speakers[0]} ` : ""}
        <b className="mono">
          {fmtTenths(sel.a)} – {fmtTenths(sel.b)}
        </b>{" "}
        · {t("{s} 秒", { s: (sel.b - sel.a).toFixed(1) })}
        {quote && ` · ${quote}`}
      </span>
      <button type="button" className="btn btn-primary btn-small" disabled={busy} onClick={() => void m.cut(null)} data-testid="ml-cut">
        {t("删掉这段")} <kbd className="ml-kbd">Del</kbd>
      </button>
      {hosts.map((tr) => (
        <button key={tr.name} type="button" className="btn btn-outline btn-small" disabled={busy} onClick={() => void m.cut(tr.name)} data-testid={`ml-mute-${tr.name}`}>
          {t("只静音 {name}", { name: tr.name })}
        </button>
      ))}
      <button type="button" className="btn btn-ghost btn-small" onClick={m.listen} data-testid="ml-listen">
        ▶ {t("听选中")}
      </button>
      <button type="button" className="btn btn-ghost btn-small" onClick={() => m.setSel(null)}>
        {t("取消")} <kbd className="ml-kbd">Esc</kbd>
      </button>
    </div>
  );
}
