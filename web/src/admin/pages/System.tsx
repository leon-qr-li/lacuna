// 系统健康: disk (and what uses it), the last backup, jobs running now (a deploy waits for them), CPU and memory
// over the last hours, server errors in the last 24 hours, and which alerts go to the owner's email.
import type { PageProps } from "../Shell";
import { t } from "../i18n";
import { PART } from "../labels";
import type { SystemData } from "../types";
import { Card, Empty, HBar, LineChart, Loading, PageHead, Pill, ago, duration, fmtBytes, fmtPct, fmtTime, useData } from "../ui";
import { Alerts } from "./Home";
import { AiCostCard } from "./AiCost";
import { StorageCard } from "./Storage";

export function SystemPage({ go, me }: PageProps) {
  const { data: s, error } = useData<SystemData>("/api/admin/system");
  if (!s)
    return (
      <>
        <PageHead title={t("系统健康")} />
        <Loading error={error} />
      </>
    );
  const backupAge = s.backup.at ? Date.now() / 1000 - s.backup.at : null;
  const samples = s.samples.slice(-48);
  const labels = samples.map((x, i) => (i === samples.length - 1 ? t("现在") : fmtTime(x.ts).split(" ").pop() ?? ""));
  const parts = Object.entries(s.parts).sort((a, b) => b[1] - a[1]);
  return (
    <>
      <PageHead title={t("系统健康")} sub={t("服务器 {n} 核 · 数据盘 {d}", { n: s.cpus, d: fmtBytes(s.disk.total) })} />
      <Alerts alerts={s.alerts} go={go} />
      <div className="a-grid g4 a-mb a-kpis">
        <section className="a-card a-kpi">
          <div className="l">{t("磁盘")}</div>
          <div className="v">{fmtPct(s.disk.pct)}</div>
          <div className={`d ${s.disk.pct >= 0.7 ? "dn" : "mu"}`}>
            {fmtBytes(s.disk.used)} / {fmtBytes(s.disk.total)}
          </div>
        </section>
        <section className="a-card a-kpi">
          <div className="l">{t("最近一次备份")}</div>
          <div className="v">{s.backup.at ? ago(s.backup.at) : t("没找到")}</div>
          <div className={`d ${backupAge === null || backupAge > 26 * 3600 ? "dn" : "up"}`}>{t("每晚备份到 R2")}</div>
        </section>
        <section className="a-card a-kpi">
          <div className="l">{t("正在跑的任务")}</div>
          <div className="v">{s.running.length}</div>
          <div className="d mu">{s.running.length ? t("现在发版会等它们跑完") : t("现在发版不会打断任何人")}</div>
        </section>
        <section className="a-card a-kpi">
          <div className="l">{t("这一版已运行")}</div>
          <div className="v">{duration(Date.now() / 1000 - s.started)}</div>
          <div className="d mu mono">v.{(s.version || "dev").slice(0, 7)}</div>
        </section>
      </div>
      <div className="a-grid g-21 a-mb">
        <Card title={t("正在进行的任务")} right={s.running.length ? <Pill tone="warn">{t("{n} 个", { n: s.running.length })}</Pill> : <Pill tone="ok">{t("空闲")}</Pill>} pad={false}>
          {s.running.length ? (
            <div className="a-tw">
              <table className="a-t">
                <thead>
                  <tr>
                    <th>{t("节目")}</th>
                    <th>{t("任务")}</th>
                    <th>{t("剧集")}</th>
                    <th>{t("开始")}</th>
                    <th style={{ width: "28%" }}>{t("进度")}</th>
                  </tr>
                </thead>
                <tbody>
                  {s.running.map((r, i) => (
                    <tr key={i}>
                      <td>{r.show}</td>
                      <td>
                        <Pill tone="info">{r.kind === "export" ? t("导出") : t("导入")}</Pill>
                      </td>
                      <td>{r.episode}</td>
                      <td className="a-muted">{ago(r.started)}</td>
                      <td>
                        {r.progress === null ? (
                          <span className="a-muted">{r.state === "queued" ? t("排队中") : t("进行中")}</span>
                        ) : (
                          <div className="a-row">
                            <div className="a-bar a-grow">
                              <i style={{ width: `${Math.round(r.progress * 100)}%` }} />
                            </div>
                            <span className="mono">{fmtPct(r.progress)}</span>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty icon="pulse" title={t("现在没有任务在跑")} sub={t("现在发版不会打断任何人。")} />
          )}
        </Card>
        <Card title={t("磁盘用在哪")} sub={s.sizes_at ? t("统计于 {t}", { t: ago(s.sizes_at) }) : t("正在统计…")}>
          <div className="a-hbars">
            {parts.map(([k, v]) => (
              <HBar key={k} label={PART[k]?.() ?? k} value={v} max={s.disk.total} text={fmtBytes(v)} tone={k === "trash" && s.disk.pct >= 0.7 ? "warn" : undefined} />
            ))}
          </div>
          <p className="a-muted small">{t("超过 70% 发告警邮件。先清回收区最快。")}</p>
        </Card>
      </div>
      {s.storage && (
        <div className="a-mb">
          <StorageCard data={s.storage} owner={me.role === "owner"} />
        </div>
      )}
      {s.ai && (
        <div className="a-mb">
          <AiCostCard data={s.ai} owner={me.role === "owner"} />
        </div>
      )}
      <div className="a-grid g2 a-mb">
        <Card title="CPU" sub={t("每 5 分钟一个点")}>
          {samples.length > 1 ? (
            <LineChart series={[samples.map((x) => x.cpu ?? 0)]} labels={labels} height={130} yfmt={(v) => `${Math.round(v)}%`} />
          ) : (
            <Empty icon="pulse" title={t("还在收集，过几分钟再看")} />
          )}
        </Card>
        <Card title={t("内存")} sub={t("每 5 分钟一个点")}>
          {samples.length > 1 ? (
            <LineChart series={[samples.map((x) => x.mem ?? 0)]} labels={labels} height={130} yfmt={(v) => `${Math.round(v)}%`} />
          ) : (
            <Empty icon="pulse" title={t("还在收集，过几分钟再看")} />
          )}
        </Card>
      </div>
      <div className="a-grid g2">
        <Card title={t("服务器报错")} sub={t("近 24 小时")} pad={false}>
          {s.errors.length ? (
            <div className="a-tw">
              <table className="a-t">
                <thead>
                  <tr>
                    <th>{t("接口")}</th>
                    <th>{t("错误")}</th>
                    <th className="n">{t("次数")}</th>
                    <th>{t("最近")}</th>
                  </tr>
                </thead>
                <tbody>
                  {s.errors.map((e, i) => (
                    <tr key={i}>
                      <td className="mono">
                        {e.method} {e.path}
                      </td>
                      <td>
                        <Pill tone="bad">{e.status}</Pill>
                      </td>
                      <td className="n">{e.n}</td>
                      <td className="a-muted">{ago(e.last)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty icon="pulse" title={t("过去 24 小时没有报错")} />
          )}
        </Card>
        <Card title={t("告警邮件")} sub={t("发到你的邮箱：每种告警一天最多一封；每天早上 8 点（温哥华）另发一封汇总")} pad={false}>
          <table className="a-t">
            <tbody>
              {[t("磁盘超过 70% 或 21 天内写满"), t("导入排队太久、本月音频接近服务器上限、内存吃紧、Access 名额快满"), t("超过 26 小时没备份"), t("导入连续失败 3 次"), t("AI 花费到预算的 80% 和 100%"), t("服务器报错"), t("维护模式开着")].map((x) => (
                <tr key={x}>
                  <td>{x}</td>
                  <td className="n">
                    <Pill tone="ok">{t("开着")}</Pill>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="a-muted small a-pad">{t("网站整个掉线时后台也打不开，这种情况由每小时的线上巡检发现。")}</p>
        </Card>
      </div>
    </>
  );
}
