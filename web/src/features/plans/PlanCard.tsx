import { useEffect, useState } from "react";
import { joinList, t } from "../../i18n";
import { plansApi, type MyPlan, type PlanLimits } from "./api";
import { MoreHours } from "./MoreHours";

const many = (n: number | null) => (n === null ? t("不限") : String(n));
const hours = (p: PlanLimits) => (p.hours_once ? t("一次性 {n} 小时", { n: p.hours ?? 0 }) : t("每月 {n} 小时", { n: many(p.hours) }));

/** 设置 → 套餐与用量 (decision 2026-10-21-plans): your plan, what you use of it, and the plans side by side.
 *  Every plan has every feature; they differ only in how much. Nobody pays yet: no payment button. */
export function PlanCard() {
  const [p, setP] = useState<MyPlan | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    plansApi.mine().then(setP, (e) => setErr((e as Error).message));
  }, []);
  if (!p) return err ? <p className="error">{err}</p> : null;
  const lim = p.limits;
  return (
    <>
      <section className="card plan-card" aria-label={t("我的套餐")} data-testid="my-plan">
        <div className="card-head">
          <h2>{t("我的套餐")}</h2>
          <span className={`plan-badge plan-${p.plan}`} data-testid="plan-name">
            {lim.name}
          </span>
        </div>
        {p.free && <p className="muted small">{t("你的套餐由 LACUNA 免费提供。")}</p>}
        <div className="plan-meters">
          <HoursMeter p={p} lim={lim} />
          <Meter label={t("节目数")} value={String(p.shows)} of={t("最多 {n} 个", { n: many(lim.shows) })} testid="plan-shows" />
        </div>
        <MoreHours />
        {p.collaborators.length > 0 && (
          <>
            <h3>{t("每个节目的协作者")}</h3>
            <ul className="plan-shows">
              {p.collaborators.map((c) => (
                <li key={c.id}>
                  <span>{c.name}</span>
                  <span className="muted">
                    {lim.collaborators === null ? t("{n} 人", { n: c.count }) : t("{n} / {max} 人", { n: c.count, max: lim.collaborators })}
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
      <section className="card plan-card" aria-label={t("所有套餐")} data-testid="plan-table">
        <h2>{t("所有套餐")}</h2>
        <p className="muted small">{t("每个套餐功能都一样，只是能用多少不同。每个节目最多 {n} 位主持人。", { n: lim.hosts })}</p>
        <table className="plan-table">
          <thead>
            <tr>
              <th />
              {p.plans.map((x) => (
                <th key={x.id} className={x.id === p.plan ? "is-mine" : ""}>
                  {x.name}
                  {x.id === p.plan && <small>{t("当前")}</small>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>{t("音频时长")}</td>
              {p.plans.map((x) => (
                <td key={x.id} className={x.id === p.plan ? "is-mine" : ""}>{hours(x)}</td>
              ))}
            </tr>
            <tr>
              <td>{t("节目数")}</td>
              {p.plans.map((x) => (
                <td key={x.id} className={x.id === p.plan ? "is-mine" : ""}>{many(x.shows)}</td>
              ))}
            </tr>
            <tr>
              <td>{t("每个节目的协作者")}</td>
              {p.plans.map((x) => (
                <td key={x.id} className={x.id === p.plan ? "is-mine" : ""}>{x.collaborators === 0 ? t("不能邀请") : many(x.collaborators)}</td>
              ))}
            </tr>
          </tbody>
        </table>
        <p className="muted small">{t("想换套餐，请回复邀请邮件联系我们。")}</p>
      </section>
    </>
  );
}

const num = (x: number) => String(Math.round(x * 10) / 10);

/** Audio hours this month: used of the allowance, a bar, and where extra hours came from. */
function HoursMeter({ p, lim }: { p: MyPlan; lim: PlanLimits }) {
  const h = p.hours;
  if (!h) return <Meter label={t("音频时长")} value="—" of={hours(lim)} />;
  const of = h.allowance === null ? t("不限") : h.once ? t("共 {n} 小时（一次性）", { n: num(h.allowance) }) : t("本月共 {n} 小时", { n: num(h.allowance) });
  const pct = h.allowance ? Math.min(100, (h.used / h.allowance) * 100) : 0;
  const extra = [
    h.bonus.granted ? t("LACUNA 加给你 {n} 小时", { n: num(h.bonus.granted) }) : null,
    h.bonus.feedback ? t("反馈被采纳奖励 {n} 小时", { n: num(h.bonus.feedback) }) : null,
  ].filter((x): x is string => !!x);
  const out = h.left !== null && h.left <= 0;
  return (
    <div className="plan-meter plan-hours" data-testid="plan-hours">
      <span className="muted small">{t("音频时长")}</span>
      <strong>{t("已用 {n} 小时", { n: num(h.used) })}</strong>
      <span className="muted small">{of}</span>
      {h.allowance !== null && (
        <span className={`plan-bar${out ? " plan-bar-out" : pct >= 80 ? " plan-bar-near" : ""}`} aria-hidden>
          <span style={{ width: `${Math.max(pct, h.used ? 2 : 0)}%` }} />
        </span>
      )}
      {extra.length > 0 && <em className="small">{t("含：{list}", { list: joinList(extra) })}</em>}
      {out ? (
        <em className="small plan-out">{h.once ? t("免费体验的时长用完了。") : t("这个月的时长用完了，下个月 1 日恢复。")}</em>
      ) : (
        !h.once && h.allowance !== null && <span className="muted small">{t("每月 1 日重新计算，按每集导入时的长度算，导入失败不算。")}</span>
      )}
    </div>
  );
}

function Meter({ label, value, of, note, testid }: { label: string; value: string; of: string; note?: string | null; testid?: string }) {
  return (
    <div className="plan-meter" data-testid={testid}>
      <span className="muted small">{label}</span>
      <strong>{value}</strong>
      <span className="muted small">{of}</span>
      {note && <em className="small">{note}</em>}
    </div>
  );
}
