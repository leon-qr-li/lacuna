// AI 用量与成本: this month's spend against the budget (email at 80% and 100%; the service never stops), cost per
// hour of audio against the $1.8 target, spend by feature, the people who cost most, how many AI edits are kept
// at review, failures. LACUNA gets text and numbers only, never audio.
import type { PageProps } from "../Shell";
import { api } from "../api";
import { t } from "../i18n";
import { CATEGORY, featureName } from "../labels";
import type { AiData } from "../types";
import { Card, Empty, HBar, Icon, LineChart, Loading, PageHead, Who, act, dialog, fmtNum, fmtPct, fmtUsd, useData } from "../ui";

export function AiPage({ me }: PageProps) {
  const { data: d, error, set } = useData<AiData>("/api/admin/ai");
  const owner = me.role === "owner";
  const editBudget = async () => {
    if (!d) return;
    const v = await dialog({
      title: t("月度 AI 预算"),
      body: t("到 80% 和 100% 各发一封邮件。到 100% 不会停服务，只提醒你。真正的硬上限在 AI 服务商的控制台里设。"),
      ok: t("保存"),
      input: { label: t("每月预算（美元）"), value: String(d.budget) },
    });
    if (!v || !(Number(v) >= 0)) return;
    const out = await act(() => api<AiData>("PUT", "/api/admin/ai/budget", { value: Number(v) }), t("预算已保存"));
    if (out) set(out);
  };
  if (!d)
    return (
      <>
        <PageHead title={t("AI 用量与成本")} />
        <Loading error={error} />
      </>
    );
  const pct = d.budget ? d.spent / d.budget : 0;
  const feats = Object.entries(d.features).sort((a, b) => b[1] - a[1]);
  const featTotal = feats.reduce((a, [, v]) => a + v, 0);
  const forecastLine = Array.from({ length: d.days }, (_, i) => (d.forecast / d.days) * (i + 1));
  const budgetLine = Array.from({ length: d.days }, () => d.budget);
  return (
    <>
      <PageHead
        title={t("AI 用量与成本")}
        sub={t("LACUNA 只拿到文字和数字，从不拿到音频。花费按每次调用的用量记录估算。")}
        actions={
          owner && (
            <button type="button" className="a-btn" onClick={editBudget} data-testid="budget-edit">
              {t("月度预算")}
            </button>
          )
        }
      />
      <div className="a-grid g4 a-mb a-kpis">
        <section className="a-card a-kpi">
          <div className="l">{t("本月花费")}</div>
          <div className="v" data-testid="ai-spent">
            {fmtUsd(d.spent)}
          </div>
          <div className="d mu">{t("预计月底 {v}", { v: fmtUsd(d.forecast) })}</div>
        </section>
        <section className="a-card a-kpi">
          <div className="l">{t("每小时音频成本")}</div>
          <div className="v">{fmtUsd(d.per_hour)}</div>
          <div className={`d ${d.per_hour !== null && d.per_hour > d.target ? "dn" : "up"}`}>{t("目标 {v}", { v: fmtUsd(d.target) })}</div>
        </section>
        <section className="a-card a-kpi">
          <div className="l">{t("预算")}</div>
          <div className="v">{fmtPct(pct)}</div>
          <div className="d mu">{t("{s} / {b}，到 80% 发邮件", { s: fmtUsd(d.spent, 0), b: fmtUsd(d.budget, 0) })}</div>
          <div className={`a-bar ${pct >= 1 ? "bad" : pct >= 0.8 ? "warn" : ""}`}>
            <i style={{ width: `${Math.min(100, pct * 100)}%` }} />
          </div>
        </section>
        <section className="a-card a-kpi">
          <div className="l">{t("本月处理的音频")}</div>
          <div className="v">{t("{n} 小时", { n: fmtNum(d.hours, 1) })}</div>
          <div className="d mu">{t("{n} 次调用", { n: d.calls })}</div>
        </section>
      </div>
      <div className="a-grid g2 a-mb">
        <Card title={t("本月累计花费")} sub={d.month}>
          <LineChart series={[d.cumulative, forecastLine, budgetLine]} labels={Array.from({ length: d.days }, (_, i) => String(i + 1))} yfmt={(v) => `$${Math.round(v)}`} names={[t("已花"), t("预计"), t("预算")]} />
        </Card>
        <Card title={t("按功能拆")} sub={t("占本月花费")}>
          {feats.length ? (
            <div className="a-hbars">
              {feats.map(([k, v]) => (
                <HBar key={k} label={featureName(k)} value={v} max={featTotal} text={`${fmtUsd(v)} · ${fmtPct(v / (featTotal || 1))}`} />
              ))}
            </div>
          ) : (
            <Empty icon="spark" title={t("本月还没有花费")} />
          )}
        </Card>
      </div>
      <div className="a-grid g-12 a-mb">
        <Card title={t("AI 剪辑保留率（按类型）")} sub={t("近 60 天的初剪，审阅时没被恢复的比例")}>
          {d.accuracy.length ? (
            <>
              <div className="a-hbars">
                {d.accuracy.map((a) => (
                  <HBar
                    key={a.category}
                    label={CATEGORY[a.category]?.() ?? a.category}
                    value={a.kept ?? 0}
                    max={1}
                    text={`${fmtPct(a.kept)} · ${a.n}`}
                    tone={a.kept !== null && a.kept < 0.7 ? "warn" : undefined}
                  />
                ))}
              </div>
              <p className="a-muted small">{t("低于 70% 标黄：说明这类剪得不准，用户常恢复。")}</p>
            </>
          ) : (
            <Empty icon="spark" title={t("还没有审阅数据")} />
          )}
        </Card>
        <Card title={t("花钱最多的 10 个人")} sub={t("按节目创建人算")} pad={false}>
          {d.top.length ? (
            <div className="a-tw">
              <table className="a-t">
                <thead>
                  <tr>
                    <th>{t("用户")}</th>
                    <th className="n">{t("音频小时")}</th>
                    <th className="n">{t("花费")}</th>
                    <th className="n">{t("每小时")}</th>
                  </tr>
                </thead>
                <tbody>
                  {d.top.map((u) => (
                    <tr key={u.email}>
                      <td>
                        <Who email={u.email} name={u.name} />
                      </td>
                      <td className="n">{fmtNum(u.hours, 1)}</td>
                      <td className="n">{fmtUsd(u.cost)}</td>
                      <td className="n">{fmtUsd(u.per_hour)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty icon="users" title={t("本月还没有花费")} />
          )}
        </Card>
      </div>
      <div className="a-grid g3">
        <Card title={t("失败")} sub={t("本月")}>
          <dl className="a-kv">
            <dt>{t("导入失败")}</dt>
            <dd>{t("{n} 次", { n: d.fails.imports })}</dd>
            <dt>{t("LACUNA 拒绝回答")}</dt>
            <dd>{t("{n} 次", { n: d.fails.refusals })}</dd>
          </dl>
          <p className="a-muted small">{t("网络或服务出错的调用不会记进用量，只能从导入失败里看出来。")}</p>
        </Card>
        <Card title={t("学到的规则")}>
          <dl className="a-kv">
            <dt>{t("本月新增")}</dt>
            <dd>{d.rules_month}</dd>
          </dl>
        </Card>
        <Card title={t("硬上限")}>
          <div className="a-row">
            <Icon name="shield" />
            <p className="a-muted small">{t("后台的预算只发提醒。想让花费到某个数就停，要在 AI 服务商控制台的 Limits 里设每月上限（只有你能改，步骤见验收清单）。")}</p>
          </div>
        </Card>
      </div>
    </>
  );
}
