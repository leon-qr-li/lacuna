import type { EditInfo, Episode } from "../api";
import { fmt, statusLabel } from "../api";
import { t } from "../i18n";
import { useListenOnly } from "../features/listen-only/state";

/** the edits within 20 seconds of the playhead (also counted on the side panel's tab) */
export const nearEdits = (ep: Episode, time: number) => ep.edits.filter((e) => e.category !== "loudness" && Math.abs(e.t - time) <= 20);

export function NearbyEdits({
  ep,
  time,
  onSeek,
  onReview,
}: {
  ep: Episode;
  time: number;
  onSeek: (t: number) => void;
  onReview: (e: EditInfo, action: "restore" | "apply") => void;
}) {
  const near = nearEdits(ep, time);
  const ro = useListenOnly();
  return (
    <section className="card" aria-label={t("当前位置附近的改动")}>
      <h2>{t("这附近改了什么")}</h2>
      {near.length === 0 ? (
        <p className="muted">{t("前后 20 秒内没有改动。")}</p>
      ) : (
        <ul className="nearby" data-testid="nearby">
          {near.map((e) => (
            <li key={e.id} data-edit={e.id} data-source={e.source}>
              <button type="button" className="linkish mono small" onClick={() => onSeek(Math.max(0, e.t - 3))}>
                {fmt(e.t)}
              </button>
              <span className="grow">{e.title}</span>
              <span className={`small status-${e.status} ${e.consequential && !e.approved ? "warn" : "muted"}`}>
                {statusLabel(e)}
              </span>
              {e.status === "applied" ? (
                <button type="button" className="btn btn-small" disabled={ro} onClick={() => onReview(e, "restore")}>
                  {t("恢复")}
                </button>
              ) : (
                <button type="button" className="btn btn-small" disabled={ro} onClick={() => onReview(e, "apply")}>
                  {t("重新应用")}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
