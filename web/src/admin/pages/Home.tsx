// 首页 (decision: 待处理 first): what needs the owner today, alerts, the key numbers with a small trend each,
// and the latest activity.
import type { PageProps } from "../Shell";
import { t } from "../i18n";
import { eventName } from "../labels";
import type { Alert, Overview } from "../types";
import { Card, Icon, LineChart, Loading, PageHead, Spark, ago, fmtBytes, fmtNum, fmtPct, fmtUsd, useData, weekLabels } from "../ui";
import { CapacityCard } from "./Capacity";

export function alertText(a: Alert): string {
  switch (a.kind) {
    case "disk":
      return t("磁盘已用 {pct}（{used} / {total}）。可以先清回收区。", { pct: fmtPct(a.pct), used: fmtBytes(a.used), total: fmtBytes(a.total) });
    case "ai":
      return t("本月 AI 花费 {spent}，到了预算 {budget} 的 {pct}。只是提醒，服务不会停。", {
        spent: fmtUsd(a.spent),
        budget: fmtUsd(a.budget, 0),
        pct: fmtPct((a.spent ?? 0) / (a.budget || 1)),
      });
    case "backup":
      return a.at ? t("超过 26 小时没有新的备份（上次 {at}）。", { at: ago(a.at) }) : t("还没有找到任何备份记录。");
    case "imports":
      return t("最近 {n} 次导入都失败了。", { n: a.n ?? 3 });
    case "errors":
      return t("过去 24 小时服务器报错 {n} 次。", { n: a.n ?? 0 });
    case "maintenance":
      return t("维护模式开着：用户现在不能上传和导入。");
    case "capacity":
      return `${a.line ?? ""}${t("。")}${a.advice ?? ""}`;
  }
}

export function Alerts({ alerts, go }: { alerts: Alert[]; go: (p: string) => void }) {
  if (!alerts.length)
    return (
      <div className="a-alerts">
        <div className="a-alert ok">
          <Icon name="shield" />
          <span>{t("系统正常：磁盘、备份、导入、LACUNA 调用都没有问题。")}</span>
        </div>
      </div>
    );
  return (
    <div className="a-alerts" data-testid="alerts">
      {alerts.map((a, i) => (
        <div key={i} className={`a-alert ${a.level === "info" ? "info" : a.level}`}>
          <Icon name="shield" />
          <span>{alertText(a)}</span>
          <button type="button" className="a-btn sm" onClick={() => go(a.kind === "ai" ? "/ai" : a.kind === "maintenance" ? "/settings" : "/system")}>
            {t("查看")}
          </button>
        </div>
      ))}
    </div>
  );
}

function greeting(name: string | null) {
  const h = new Date().getHours();
  const who = name || "";
  if (h < 11) return t("早上好，{name}", { name: who });
  if (h < 18) return t("下午好，{name}", { name: who });
  return t("晚上好，{name}", { name: who });
}

export function Home({ me, go }: PageProps) {
  const { data: o, error } = useData<Overview>("/api/admin/overview");
  if (!o) return <Loading error={error} />;
  const td = o.todo;
  const total = td.fb + td.hours + td.trial + td.collab;
  const todo: [string, string, string, string, number][] = [
    ["inbox", "/feedback", t("新反馈"), t("还没处理的反馈"), td.fb],
    ["clock", "/hours", t("加时长申请"), t("等你批准"), td.hours],
    ["hand", "/access", t("试用申请"), t("登录页提交的"), td.trial],
    ["users", "/access?tab=collab", t("协作者申请"), t("节目管理员想拉人进来"), td.collab],
  ];
  const k = o.kpi;
  const delta = (n: number, unit: string) => (n > 0 ? `+${n} ${unit}` : n < 0 ? `${n} ${unit}` : t("和上周一样"));
  const days = o.ai.days;
  const spentLine = o.ai.cumulative;
  const forecastLine = Array.from({ length: days }, (_, i) => (o.ai.forecast / days) * (i + 1));
  return (
    <>
      <PageHead title={greeting(me.name)} sub={t("今天要你处理的事，以及全站的几个关键数字。")} />
      <Alerts alerts={o.alerts} go={go} />
      <div className="a-grid g-21">
        <Card title={t("待处理")} sub={t("{n} 件", { n: total })} testid="todo">
          <div className="a-todo">
            {todo.map(([icon, path, title, sub, n]) => (
              <button key={title} type="button" onClick={() => go(path)}>
                <span className="ic">
                  <Icon name={icon} />
                </span>
                <span>
                  <b>{title}</b>
                  <span className="s">{sub}</span>
                </span>
                <span className={`num${n ? "" : " z"}`}>{n}</span>
                <span className="arr">›</span>
              </button>
            ))}
          </div>
        </Card>
        <Card title={t("最近动态")}>
          {o.activity.length ? (
            <div className="a-tl">
              {o.activity.map((a, i) => (
                <div key={i}>
                  <time>{ago(a.ts)}</time>
                  <b>{a.name || a.who || t("有人")}</b> {eventName(a.ev)}
                  {a.show ? ` · ${a.show}` : ""}
                  {a.ep ? ` · ${a.ep}` : ""}
                </div>
              ))}
            </div>
          ) : (
            <p className="a-muted">{t("还没有动态。")}</p>
          )}
        </Card>
      </div>
      <div className="a-grid g5 a-kpis">
        <Kpi label={t("账号总数")} value={fmtNum(k.accounts.value)} sub={delta(k.accounts.delta, t("本周"))} tone={k.accounts.delta > 0 ? "up" : "mu"} spark={k.accounts.spark} />
        <Kpi label={t("周活跃")} value={fmtNum(k.wau.value)} sub={delta(k.wau.delta, t("比上周"))} tone={k.wau.delta > 0 ? "up" : k.wau.delta < 0 ? "dn" : "mu"} spark={k.wau.spark} />
        <Kpi label={t("本周导出")} value={fmtNum(k.exports.value)} sub={delta(k.exports.delta, t("比上周"))} tone={k.exports.delta > 0 ? "up" : "mu"} spark={k.exports.spark} />
        <Kpi label={t("本月 AI 花费")} value={fmtUsd(k.ai.value, 0)} sub={t("预计月底 {v}", { v: fmtUsd(k.ai.forecast, 0) })} tone={k.ai.forecast > k.ai.budget ? "dn" : "mu"} spark={k.ai.spark} />
        <Kpi label={t("磁盘")} value={fmtPct(k.disk.value)} sub={`${fmtBytes(k.disk.used)} / ${fmtBytes(k.disk.total)}`} tone={k.disk.value >= 0.7 ? "dn" : "mu"} spark={[k.disk.value, k.disk.value]} />
      </div>
      {o.capacity && (
        <div className="a-mb">
          <CapacityCard measures={o.capacity} />
        </div>
      )}
      <div className="a-grid g2">
        <Card title={t("周活跃")} sub={t("近 8 周")} right={<button type="button" className="a-btn ghost sm" onClick={() => go("/growth")}>{t("增长与留存 →")}</button>}>
          <LineChart series={[o.wau]} labels={weekLabels(o.wau.length)} />
        </Card>
        <Card
          title={t("本月 AI 花费")}
          sub={t("已花 {spent} · 预计 {forecast} · 预算 {budget}", { spent: fmtUsd(o.ai.spent), forecast: fmtUsd(o.ai.forecast), budget: fmtUsd(o.ai.budget, 0) })}
          right={<button type="button" className="a-btn ghost sm" onClick={() => go("/ai")}>{t("AI 成本 →")}</button>}
        >
          <LineChart series={[spentLine, forecastLine]} labels={Array.from({ length: days }, (_, i) => String(i + 1))} yfmt={(v) => `$${Math.round(v)}`} names={[t("已花"), t("预计")]} />
        </Card>
      </div>
    </>
  );
}

export function Kpi({ label, value, sub, tone, spark }: { label: string; value: string; sub: string; tone: "up" | "dn" | "mu"; spark: number[] }) {
  return (
    <section className="a-card a-kpi">
      <div className="l">{label}</div>
      <div className="v">{value}</div>
      <div className={`d ${tone}`}>{sub}</div>
      <Spark values={spark} tone={tone} />
    </section>
  );
}
