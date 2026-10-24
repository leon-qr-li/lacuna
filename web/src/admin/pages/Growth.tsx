// 增长与留存: from the server's event log (numbers and feature names only, never text or audio): activation,
// weekly actives, sign-ups, the episode funnel and the time between steps, feature use, weekly retention by
// sign-up week, interface languages, and regions (from the new-show questions).
import { useState } from "react";
import type { PageProps } from "../Shell";
import { t } from "../i18n";
import { REGION, STEP, featureName } from "../labels";
import type { GrowthData } from "../types";
import { Bars, Card, Empty, HBar, Loading, PageHead, Spark, duration, fmtDate, fmtNum, fmtPct, useData, weekLabels } from "../ui";

export function GrowthPage(_: PageProps) {
  const [weeks, setWeeks] = useState(8);
  const { data: g, error } = useData<GrowthData>(`/api/admin/growth?weeks=${weeks}`);
  const range = (
    <div className="a-tg" role="group" aria-label={t("时间范围")}>
      {[8, 13, 26].map((w) => (
        <button key={w} type="button" aria-pressed={weeks === w} onClick={() => setWeeks(w)}>
          {t("{n} 周", { n: w })}
        </button>
      ))}
    </div>
  );
  if (!g)
    return (
      <>
        <PageHead title={t("增长与留存")} actions={range} />
        <Loading error={error} />
      </>
    );
  const langTotal = Object.values(g.langs).reduce((a, b) => a + b, 0) || 1;
  const max = Math.max(1, g.funnel[0]?.n ?? 0);
  const regionMax = Math.max(1, ...Object.values(g.regions));
  return (
    <>
      <PageHead title={t("增长与留存")} sub={t("数据来自服务器的事件日志，只记录数字和功能名，不记文字和音频。原始记录保留 13 个月。")} actions={range} />
      <div className="a-grid g4 a-mb a-kpis">
        <section className="a-card a-kpi">
          <div className="l">{t("激活率")}</div>
          <div className="v">{fmtPct(g.activation.rate)}</div>
          <div className="d mu">{t("注册 7 天内导出第一集 · {n} / {of}", { n: g.activation.n, of: g.activation.of })}</div>
        </section>
        <section className="a-card a-kpi">
          <div className="l">{t("周活跃")}</div>
          <div className="v">{fmtNum(g.wau[g.wau.length - 1])}</div>
          <div className="d mu">{t("7 天内动过手")}</div>
          <Spark values={g.wau} tone="up" />
        </section>
        <section className="a-card a-kpi">
          <div className="l">{t("每人每月剧集")}</div>
          <div className="v">{fmtNum(g.per_user_month, 1)}</div>
          <div className="d mu">{t("近 30 天 · {n} 个活跃用户", { n: g.active_month })}</div>
        </section>
        <section className="a-card a-kpi">
          <div className="l">{t("中文 / 英文")}</div>
          <div className="v">
            {fmtPct((g.langs.zh ?? 0) / langTotal)} / {fmtPct((g.langs.en ?? 0) / langTotal)}
          </div>
          <div className="d mu">{t("界面语言")}</div>
        </section>
      </div>
      <div className="a-grid g2 a-mb">
        <Card title={t("每集的漏斗")} sub={t("所有剧集，每一步第一次发生")}>
          {g.funnel[0]?.n ? (
            <div className="a-funnel">
              {g.funnel.map((f, i) => (
                <div key={f.step} className="a-fs">
                  <span>{STEP[f.step]?.() ?? f.step}</span>
                  <div>
                    <div className="fb" style={{ width: `${Math.max(4, (f.n / max) * 100)}%` }}>
                      {f.n}
                    </div>
                  </div>
                  <span className="dr">{i ? t("{p} 走到这步", { p: fmtPct(f.n / Math.max(1, g.funnel[i - 1].n)) }) : ""}</span>
                </div>
              ))}
            </div>
          ) : (
            <Empty icon="chart" title={t("还没有剧集")} />
          )}
        </Card>
        <Card title={t("每周新注册")}>
          <Bars values={g.signups} labels={weekLabels(g.signups.length)} />
        </Card>
      </div>
      <div className="a-grid g2 a-mb">
        <Card title={t("周留存")} sub={t("按注册那一周分组，之后第 N 周还在用的比例")}>
          <Cohorts g={g} />
        </Card>
        <Card title={t("每步用时（中位数）")} pad={false}>
          <table className="a-t">
            <tbody>
              {g.durations.map((s) => (
                <tr key={s.from}>
                  <td>
                    {STEP[s.from]?.() ?? s.from} → {STEP[s.to]?.() ?? s.to}
                  </td>
                  <td className="n">{duration(s.median)}</td>
                  <td className="n a-muted">{t("{n} 集", { n: s.n })}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>
      <div className="a-grid g2">
        <Card title={t("功能使用率")} sub={t("近 30 天用过的活跃用户占比")}>
          <div className="a-hbars">
            {g.features.map((f) => (
              <HBar key={f.feature} label={featureName(f.feature)} value={f.pct ?? 0} max={1} text={fmtPct(f.pct)} />
            ))}
          </div>
        </Card>
        <Card title={t("地区")} sub={t("来自新节目的问题，不记录 IP")}>
          {Object.keys(g.regions).length ? (
            <div className="a-hbars">
              {Object.entries(g.regions)
                .sort((a, b) => b[1] - a[1])
                .map(([k, v]) => (
                  <HBar key={k} label={REGION[k]?.() ?? k} value={v} max={regionMax} text={String(v)} />
                ))}
            </div>
          ) : (
            <Empty icon="chart" title={t("还没有人回答")} />
          )}
        </Card>
      </div>
    </>
  );
}

function Cohorts({ g }: { g: GrowthData }) {
  const n = Math.max(0, ...g.cohorts.map((c) => c.weeks.length));
  if (!g.cohorts.some((c) => c.size)) return <Empty icon="chart" title={t("近 6 周没有新注册")} />;
  return (
    <div className="a-heat" style={{ gridTemplateColumns: `minmax(90px,auto) repeat(${n}, minmax(0,1fr))` }}>
      <div className="h">{t("注册周")}</div>
      {Array.from({ length: n }, (_, i) => (
        <div key={i} className="h c">
          +{i}
        </div>
      ))}
      {g.cohorts.map((c) => (
        <Row key={c.start} start={c.start} size={c.size} weeks={c.weeks} n={n} />
      ))}
    </div>
  );
}

function Row({ start, size, weeks, n }: { start: number; size: number; weeks: (number | null)[]; n: number }) {
  return (
    <>
      <div className="h">
        {fmtDate(start)} <span className="a-muted">· {size}</span>
      </div>
      {Array.from({ length: n }, (_, j) => {
        const v = size ? weeks[j] : null;
        if (v === null || v === undefined) return <div key={j} />;
        const pct = Math.round(v * 100);
        return (
          <div key={j} style={{ background: `color-mix(in srgb, var(--acc) ${Math.round(pct * 0.85)}%, var(--heat0))`, color: pct > 55 ? "var(--on-acc)" : "var(--ink-2)" }}>
            {pct}%
          </div>
        );
      })}
    </>
  );
}
