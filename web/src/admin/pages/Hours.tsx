// 时长申请: requests from 「想要更多时长」 (the owner approves each one; nothing is added on its own), usage against
// the allowance, plans and the beta end date, and who said they would pay.
import { useState } from "react";
import { api } from "../api";
import type { PageProps } from "../Shell";
import { t } from "../i18n";
import { planName } from "../labels";
import type { HourReq, HoursData } from "../types";
import { Card, Empty, Icon, Loading, PageHead, Pill, Tabs, Who, act, ago, fmtDate, fmtNum, useData } from "../ui";

type Tab = "req" | "usage" | "plans" | "pay" | "done";

export function HoursPage({ me }: PageProps) {
  const [tab, setTab] = useState<Tab>("req");
  const { data, error, set } = useData<HoursData>("/api/admin/hours");
  const owner = me.role === "owner";
  return (
    <>
      <PageHead title={t("时长申请")} sub={t("用户点「想要更多时长」的申请。每一条都由你批，不会自动加时长。")} />
      <div className="a-alert warn a-mb">
        <Icon name="clock" />
        <span>{t("规则还没定：beta 时长、到期以后怎么收费，等商业模式定了再填。用量要等第 5 批做完额度计量才有数字。")}</span>
      </div>
      {!data ? (
        <Loading error={error} />
      ) : (
        <>
          <Tabs<Tab>
            value={tab}
            onChange={setTab}
            items={[
              { id: "req", label: t("待批"), n: data.requests.length },
              { id: "usage", label: t("用量对比额度") },
              { id: "plans", label: t("套餐与 beta") },
              { id: "pay", label: t("付费意向"), n: data.willing.length },
              { id: "done", label: t("处理过的") },
            ]}
          />
          {tab === "req" && <Pending data={data} set={set} owner={owner} />}
          {tab === "usage" && <Usage data={data} />}
          {tab === "plans" && <Plans data={data} set={set} owner={owner} />}
          {tab === "pay" && <Willing data={data} />}
          {tab === "done" && <Decided rows={data.decided} />}
        </>
      )}
    </>
  );
}

function Pending({ data, set, owner }: { data: HoursData; set: (d: HoursData) => void; owner: boolean }) {
  if (!data.requests.length)
    return (
      <Card>
        <Empty icon="clock" title={t("没有待批的申请")} sub={t("beta 用户用完时长以后点「想要更多时长」，申请会出现在这里。")} />
      </Card>
    );
  return (
    <div className="a-cards-phone">
      {data.requests.map((r) => (
        <Request key={r.id} r={r} set={set} owner={owner} />
      ))}
    </div>
  );
}

function Request({ r, set, owner }: { r: HourReq; set: (d: HoursData) => void; owner: boolean }) {
  const [hours, setHours] = useState(r.hours);
  const decide = async (action: "approve" | "decline") => {
    const out = await act(
      () => api<HoursData>("POST", `/api/admin/hours/${r.id}`, { action, hours: action === "approve" ? hours : undefined }),
      action === "approve" ? t("已批准，已发邮件告诉对方") : t("已拒绝，已通知对方"),
    );
    if (out) set(out);
  };
  return (
    <Card className="a-req" testid="hour-request">
      <div className="a-row wrap">
        <Who email={r.email} name={r.name} />
        <Pill>{planName(r.plan)}</Pill>
        {r.would_pay && <Pill tone="ok">{t("愿意付费")}</Pill>}
        <span className="spacer" />
        <span className="a-muted small">{ago(r.created)}</span>
      </div>
      <p className="a-quote">{r.reason || t("（没写理由）")}</p>
      <div className="a-row wrap">
        <span className="a-muted">{t("想要 {n} 小时", { n: fmtNum(r.hours, 1) })}</span>
        <span className="spacer" />
        <label className="a-row small">
          {t("批")}
          <select className="a-inp sm" value={hours} onChange={(e) => setHours(Number(e.target.value))} aria-label={t("批几个小时")} disabled={!owner}>
            {[...new Set([1, 2, 3, 4, 6, 8, r.hours])].sort((a, b) => a - b).map((n) => (
              <option key={n} value={n}>
                {t("{n} 小时", { n })}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="a-btn" disabled={!owner} onClick={() => decide("decline")} data-testid="hours-decline">
          {t("拒绝")}
        </button>
        <button type="button" className="a-btn acc" disabled={!owner} onClick={() => decide("approve")} data-testid="hours-approve">
          {t("批准")}
        </button>
      </div>
      {!owner && <p className="a-muted small">{t("只有站长能批时长。")}</p>}
    </Card>
  );
}

function Usage({ data }: { data: HoursData }) {
  if (!data.usage.length)
    return (
      <Card>
        <Empty icon="users" title={t("还没有成员")} />
      </Card>
    );
  const rows = [...data.usage].sort((a, b) => (b.used ?? 0) / (b.hours || 1) - (a.used ?? 0) / (a.hours || 1));
  return (
    <Card pad={false}>
      <div className="a-tw">
        <table className="a-t">
          <thead>
            <tr>
              <th>{t("用户")}</th>
              <th>{t("套餐")}</th>
              <th style={{ width: "40%" }}>{t("本月用量")}</th>
              <th className="n">{t("已用 / 额度")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((u) => {
              const p = u.used !== null && u.hours ? (u.used / u.hours) * 100 : 0;
              return (
                <tr key={u.email}>
                  <td>
                    <Who email={u.email} name={u.name} />
                  </td>
                  <td>
                    <Pill>{planName(u.plan)}</Pill>
                  </td>
                  <td>
                    {u.used === null ? (
                      <span className="a-muted small">{t("计量第 5 批上线")}</span>
                    ) : (
                      <div className={`a-bar ${p >= 100 ? "bad" : p >= 80 ? "warn" : ""}`}>
                        <i style={{ width: `${Math.min(100, p)}%` }} />
                      </div>
                    )}
                  </td>
                  <td className="n">
                    {u.used === null ? "—" : fmtNum(u.used, 1)} / {u.hours === null ? "∞" : fmtNum(u.hours)} h
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function Plans({ data, set, owner }: { data: HoursData; set: (d: HoursData) => void; owner: boolean }) {
  const [end, setEnd] = useState(data.beta_end ?? "");
  const save = async () => {
    const out = await act(() => api<HoursData>("PUT", "/api/admin/hours/settings", { beta_end: end || null }), t("beta 截止日期已保存"));
    if (out) set(out);
  };
  return (
    <div className="a-grid g2">
      <Card title={t("beta 截止日期")}>
        <dl className="a-kv">
          <dt>{t("截止")}</dt>
          <dd className="a-row">
            <input className="a-inp" type="date" value={end} onChange={(e) => setEnd(e.target.value)} disabled={!owner} aria-label={t("截止")} data-testid="beta-end" />
            <button type="button" className="a-btn" disabled={!owner || end === (data.beta_end ?? "")} onClick={save}>
              {t("保存")}
            </button>
          </dd>
          <dt>{t("现在")}</dt>
          <dd>{data.beta_end ? fmtDate(Date.parse(data.beta_end) / 1000) : t("待定")}</dd>
          <dt>{t("到期以后")}</dt>
          <dd className="a-muted">{t("等商业模式定")}</dd>
        </dl>
      </Card>
      <Card title={t("套餐")} pad={false}>
        <table className="a-t">
          <thead>
            <tr>
              <th>{t("套餐")}</th>
              <th className="n">{t("每月小时")}</th>
              <th className="n">{t("节目")}</th>
              <th className="n">{t("搭档人数")}</th>
            </tr>
          </thead>
          <tbody>
            {data.plans.map((p) => (
              <tr key={p.id}>
                <td>
                  {planName(p.id)}
                  {p.hours_once && <span className="a-muted small"> · {t("只给一次")}</span>}
                </td>
                <td className="n">{p.hours ?? "∞"}</td>
                <td className="n">{p.shows ?? "∞"}</td>
                <td className="n">{p.collaborators ?? "∞"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="a-muted small a-pad">{t("套餐的数字写在代码里，改它们要发一版。")}</p>
      </Card>
    </div>
  );
}

function Willing({ data }: { data: HoursData }) {
  if (!data.willing.length)
    return (
      <Card>
        <Empty icon="star" title={t("还没有人表示愿意付费")} sub={t("用户申请时长时勾了「愿意付费」，会出现在这里。")} />
      </Card>
    );
  return (
    <Card pad={false}>
      <div className="a-tw">
        <table className="a-t">
          <thead>
            <tr>
              <th>{t("用户")}</th>
              <th>{t("在哪表示的")}</th>
              <th>{t("原话")}</th>
              <th>{t("时间")}</th>
            </tr>
          </thead>
          <tbody>
            {data.willing.map((w, i) => (
              <tr key={i}>
                <td>
                  <Who email={w.email} name={w.name} />
                </td>
                <td>{t("加时长申请")}</td>
                <td className="wrap">{w.reason || "—"}</td>
                <td className="a-muted">{ago(w.at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function Decided({ rows }: { rows: HourReq[] }) {
  if (!rows.length)
    return (
      <Card>
        <Empty icon="clock" title={t("还没有处理过的申请")} />
      </Card>
    );
  return (
    <Card pad={false}>
      <div className="a-tw">
        <table className="a-t">
          <thead>
            <tr>
              <th>{t("用户")}</th>
              <th>{t("结果")}</th>
              <th className="n">{t("小时")}</th>
              <th>{t("理由")}</th>
              <th>{t("处理时间")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>
                  <Who email={r.email} name={r.name} />
                </td>
                <td>{r.status === "approved" ? <Pill tone="ok">{t("批准")}</Pill> : <Pill>{t("拒绝")}</Pill>}</td>
                <td className="n">{r.status === "approved" ? fmtNum(r.granted ?? r.hours, 1) : "—"}</td>
                <td className="wrap a-muted">{r.reason || "—"}</td>
                <td className="a-muted">{ago(r.decided_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
