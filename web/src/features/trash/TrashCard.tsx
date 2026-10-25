import { useEffect, useState } from "react";
import { fmtDate, t } from "../../i18n";
import { confirmDialog } from "../dialog/Dialog";
import { trashApi, type TrashItem, type TrashList } from "./api";
import "./trash.css";

/** 设置 → 成员与邀请, for the site owner and admins: shows and accounts deleted in the last 60 days, each with
 *  恢复 (decision 2026-10-24-deleted-kept-60-days). After 60 days they are gone for good. */
export function TrashCard() {
  const [list, setList] = useState<TrashList | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    trashApi.list().then(setList, (e) => setErr((e as Error).message));
  }, []);
  const restore = async (x: TrashItem) => {
    const ok = await confirmDialog({
      title: x.kind === "show" ? t("恢复节目「{name}」？", { name: x.name }) : t("恢复账号 {name}？", { name: x.name }),
      message: x.kind === "show" ? t("节目回到原来的成员手里，先是已归档状态，管理员在节目设置里恢复后就能继续剪。") : t("账号和它原来所在的节目都会回来，可以用原来的密码登录。"),
      confirmLabel: t("恢复"),
    });
    if (!ok) return;
    setErr(null);
    try {
      setList(await trashApi.restore(x));
    } catch (e) {
      setErr((e as Error).message);
    }
  };
  return (
    <section className="card" aria-label={t("回收区")} data-testid="trash-card">
      <h2>{t("回收区")}</h2>
      <p className="muted small">{t("删除的节目和账号保留 60 天，期间可以恢复；满 60 天后彻底清除。")}</p>
      {list && !list.items.length && <p className="muted" data-testid="trash-empty">{t("回收区是空的。")}</p>}
      {!!list?.items.length && (
        <ul className="trash-list">
          {list.items.map((x) => (
            <li key={`${x.kind}:${x.id}`} data-testid="trash-item">
              <span className="grow">
                <strong>{x.name}</strong>
                <span className="muted small">
                  {" · "}
                  {x.kind === "show" ? t("节目") : t("账号")}
                  {" · "}
                  {t("{date} 删除", { date: fmtDate(x.deleted_at * 1000) })}
                  {x.by && ` · ${x.by}`}
                  {" · "}
                  {t("还剩 {n} 天", { n: x.left_days })}
                </span>
              </span>
              <button type="button" className="btn btn-outline btn-small" onClick={() => void restore(x)} data-testid="trash-restore">
                {t("恢复")}
              </button>
            </li>
          ))}
        </ul>
      )}
      {err && <p className="error small">{err}</p>}
    </section>
  );
}
