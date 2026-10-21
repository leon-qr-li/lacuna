import { useEffect, useState } from "react";
import { t } from "../../i18n";
import { plansApi, type MyPlan, type PlanLimits } from "./api";

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
          <Meter label={t("音频时长")} value={p.hours_used === null ? "—" : String(p.hours_used)} of={hours(lim)} note={p.hours_used === null ? t("计时稍后开放") : null} />
          <Meter label={t("节目数")} value={String(p.shows)} of={t("最多 {n} 个", { n: many(lim.shows) })} testid="plan-shows" />
        </div>
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
