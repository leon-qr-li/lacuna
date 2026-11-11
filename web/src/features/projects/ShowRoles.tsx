import { useEffect, useState } from "react";
import { fmtDateTime, t } from "../../i18n";
import { spacesApi, type ProjectPeople } from "../spaces/api";

/** What each show role may do (decision 2026-10-21-roles; enforced in lacuna_app/routes/spaces.py). */
const MATRIX: { what: string; admin: boolean; editor: boolean; viewer: boolean }[] = [
  { what: t("试听、看剧集和逐字稿"), admin: true, editor: true, viewer: true },
  { what: t("导入、剪辑、导出"), admin: true, editor: true, viewer: false },
  { what: t("邀请和移出协作者"), admin: true, editor: false, viewer: false },
  { what: t("改节目设置"), admin: true, editor: false, viewer: false },
  { what: t("归档、永久删除"), admin: true, editor: false, viewer: false },
];

export function RoleMatrix() {
  return (
    <div className="prj-matrix" data-testid="role-matrix">
      <h3>{t("角色能做什么")}</h3>
      <table>
        <thead>
          <tr>
            <th />
            <th>{t("管理员")}</th>
            <th>{t("剪辑师")}</th>
            <th>{t("只听")}</th>
          </tr>
        </thead>
        <tbody>
          {MATRIX.map((r) => (
            <tr key={r.what}>
              <td>{r.what}</td>
              {([r.admin, r.editor, r.viewer] as const).map((on, i) => (
                <td key={i} className={on ? "is-on" : ""} aria-label={on ? t("可以") : t("不可以")}>
                  {on ? "✓" : "—"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** 「允许 LACUNA 支持查看」: the show's admins let LACUNA support open it read-only for 7 days. Nobody
 *  at LACUNA sees a show otherwise, not even the site owner. */
export function SupportAccess({ id, manage }: { id: string; manage: boolean }) {
  const [p, setP] = useState<ProjectPeople | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    spacesApi.people(id).then(setP, (e) => setErr((e as Error).message));
  }, [id]);
  if (!p) return err ? <p className="error small">{err}</p> : null;
  const on = !!p.support_until && p.support_until * 1000 > Date.now();
  const flip = async () => {
    setBusy(true);
    setErr(null);
    try {
      setP(await spacesApi.support(id, !on));
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="prj-support" data-testid="support-access">
      <div>
        <strong>{t("允许 LACUNA 支持查看")}</strong>
        <p className="muted small">
          {on
            ? t("已打开：LACUNA 支持可以只读查看这个节目，到 {until} 自动关闭。", { until: fmtDateTime(p.support_until! * 1000) })
            : t("平时谁都看不到你的节目，LACUNA 的工作人员也不行。需要帮忙时打开，LACUNA 支持能只读查看 7 天，到期自动关闭。")}
        </p>
        {err && <p className="error small">{err}</p>}
      </div>
      {manage && (
        <button type="button" className={on ? "btn btn-outline" : "btn btn-primary"} disabled={busy} onClick={() => void flip()} data-testid="support-toggle">
          {on ? t("关闭") : t("打开 7 天")}
        </button>
      )}
    </div>
  );
}
