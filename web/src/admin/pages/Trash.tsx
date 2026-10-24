// 回收区: deleted shows and accounts stay here 60 days, then go for good (people see 「永久删除」). Restoring asks
// for the code again; 立即清除 is the owner's, with the name typed.
import type { PageProps } from "../Shell";
import { api } from "../api";
import { t } from "../i18n";
import type { TrashData } from "../types";
import { Card, Empty, Loading, PageHead, Pill, act, dialog, fmtBytes, fmtDate, useData } from "../ui";

export function TrashPage({ me }: PageProps) {
  const { data, error, set } = useData<TrashData>("/api/admin/trash");
  const owner = me.role === "owner";
  const restore = async (kind: string, id: string, name: string) => {
    const ok = await dialog({ title: t("恢复「{name}」？", { name }), body: kind === "show" ? t("节目回到原来的成员手里。") : t("账号恢复，回到原来还在的节目里。"), ok: t("恢复") });
    if (ok === null) return;
    const out = await act(() => api<TrashData>("POST", `/api/admin/trash/${kind}/${encodeURIComponent(id)}/restore`), t("已恢复"));
    if (out) set(out);
  };
  const purge = async (kind: string, id: string, name: string) => {
    const typed = await dialog({ title: t("立即清除？"), body: t("从回收区清除「{name}」，不能恢复。", { name }), ok: t("立即清除"), danger: true, typed: name });
    if (typed === null) return;
    const out = await act(() => api<TrashData>("POST", `/api/admin/trash/${kind}/${encodeURIComponent(id)}/purge`, { confirm: typed }), t("已清除"));
    if (out) set(out);
  };
  const items = data?.items ?? [];
  const size = items.reduce((a, i) => a + (i.size ?? 0), 0);
  return (
    <>
      <PageHead title={t("回收区")} sub={t("删除的节目和账号在这里保留 {n} 天，然后自动清除。用户看到的是「永久删除」。", { n: data?.keep_days ?? 60 })} />
      {!data ? (
        <Loading error={error} />
      ) : (
        <>
          <div className="a-grid g3 a-mb">
            <section className="a-card a-kpi">
              <div className="l">{t("节目")}</div>
              <div className="v">{items.filter((i) => i.kind === "show").length}</div>
            </section>
            <section className="a-card a-kpi">
              <div className="l">{t("账号")}</div>
              <div className="v">{items.filter((i) => i.kind === "user").length}</div>
            </section>
            <section className="a-card a-kpi">
              <div className="l">{t("占用空间")}</div>
              <div className="v">{fmtBytes(size)}</div>
            </section>
          </div>
          {!items.length ? (
            <Card>
              <Empty icon="trash" title={t("回收区是空的")} sub={t("删除的节目和账号会在这里保留 60 天。")} />
            </Card>
          ) : (
            <Card pad={false}>
              <div className="a-tw">
                <table className="a-t a-t-cards">
                  <thead>
                    <tr>
                      <th>{t("类型")}</th>
                      <th>{t("名称")}</th>
                      <th>{t("谁删的")}</th>
                      <th>{t("删除日期")}</th>
                      <th>{t("剩余")}</th>
                      <th className="n">{t("大小")}</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((i) => {
                      const name = i.name || i.id;
                      return (
                        <tr key={`${i.kind}/${i.id}`} data-testid="trash-row">
                          <td>
                            <Pill>{i.kind === "show" ? t("节目") : t("账号")}</Pill>
                          </td>
                          <td data-label={t("名称")}>{name}</td>
                          <td className="a-muted" data-label={t("谁删的")}>
                            {i.by || "—"}
                          </td>
                          <td className="mono" data-label={t("删除日期")}>
                            {fmtDate(i.deleted_at)}
                          </td>
                          <td data-label={t("剩余")}>{i.left_days < 10 ? <Pill tone="warn">{t("{n} 天", { n: i.left_days })}</Pill> : t("{n} 天", { n: i.left_days })}</td>
                          <td className="n" data-label={t("大小")}>
                            {fmtBytes(i.size)}
                          </td>
                          <td>
                            <div className="a-row end">
                              <button type="button" className="a-btn sm" onClick={() => restore(i.kind, i.id, name)} data-testid="trash-restore">
                                {t("恢复")}
                              </button>
                              {owner && (
                                <button type="button" className="a-btn sm danger" onClick={() => purge(i.kind, i.id, name)} data-testid="trash-purge">
                                  {t("立即清除")}
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </>
      )}
    </>
  );
}
