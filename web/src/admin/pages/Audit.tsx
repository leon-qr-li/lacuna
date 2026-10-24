// 操作日志: every change made in the admin, newest first; nothing here can be deleted. "Older" pages back by time.
import { useState } from "react";
import { get } from "../api";
import type { PageProps } from "../Shell";
import { t } from "../i18n";
import { actionName } from "../labels";
import type { AuditRow } from "../types";
import { Card, Empty, Loading, PageHead, Pill, Who, fmtTime, isDemo, useData } from "../ui";

// actions that only go through after the code is entered again
const STEPUP = new Set([
  "user.update",
  "user.delete",
  "user.erase",
  "user.sessions.end",
  "hours.give",
  "hours.approve",
  "site.new_members",
  "site.maintenance",
  "staff.role",
  "trash.restore.show",
  "trash.restore.user",
  "trash.purge.show",
  "trash.purge.user",
  "feedback.prompt_reset",
]);

function detail(r: AuditRow): string {
  const d = r.data || {};
  const parts: string[] = [];
  for (const [k, v] of Object.entries(d)) {
    if (v === null || v === undefined || v === false || v === "") continue;
    parts.push(v === true ? k : `${k}: ${String(v)}`);
  }
  return parts.join(" · ");
}

export function AuditPage(_: PageProps) {
  const { data, error } = useData<{ rows: AuditRow[] }>("/api/admin/audit");
  const [more, setMore] = useState<AuditRow[]>([]);
  const [end, setEnd] = useState(false);
  const rows = data ? [...data.rows, ...more] : [];
  const older = async () => {
    if (isDemo() || !rows.length) return setEnd(true);
    const r = await get<{ rows: AuditRow[] }>(`/api/admin/audit?before=${rows[rows.length - 1].ts}`);
    setMore([...more, ...r.rows]);
    if (r.rows.length < 200) setEnd(true);
  };
  return (
    <>
      <PageHead title={t("操作日志")} sub={t("后台里每一次改动都记在这里，不能删除。")} />
      {!data ? (
        <Loading error={error} />
      ) : !rows.length ? (
        <Card>
          <Empty icon="log" title={t("还没有记录")} />
        </Card>
      ) : (
        <>
          <Card pad={false}>
            <div className="a-tw">
              <table className="a-t a-t-cards">
                <thead>
                  <tr>
                    <th>{t("时间")}</th>
                    <th>{t("谁")}</th>
                    <th>{t("做了什么")}</th>
                    <th>{t("对象")}</th>
                    <th>{t("细节")}</th>
                    <th>{t("验证")}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.id} data-testid="audit-row">
                      <td className="mono">{fmtTime(r.ts)}</td>
                      <td data-label={t("谁")}>
                        <Who email={r.email} />
                      </td>
                      <td data-label={t("做了什么")}>{actionName(r.action)}</td>
                      <td className="wrap" data-label={t("对象")}>
                        {r.target || "—"}
                      </td>
                      <td className="wrap a-muted small" data-label={t("细节")}>
                        {detail(r) || "—"}
                      </td>
                      <td data-label={t("验证")}>{STEPUP.has(r.action) ? <Pill tone="ok">{t("验证码")}</Pill> : <span className="a-muted">—</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
          {data.rows.length >= 200 && !end && (
            <div className="a-row end a-mt">
              <button type="button" className="a-btn" onClick={older}>
                {t("更早的")}
              </button>
            </div>
          )}
        </>
      )}
    </>
  );
}
