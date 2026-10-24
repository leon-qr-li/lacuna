// 邀请与申请: beta is invite-only and every new person is approved by the owner. Trial requests (login page),
// co-host requests (a show admin wants someone without an account), pending invites, the waitlist, beta seats
// (counted by show), where people came from, and the 「新成员需站长批准」 switch.
import { useState } from "react";
import { api } from "../api";
import type { PageProps } from "../Shell";
import { t } from "../i18n";
import { ROLE, TRACKS, planName, sourceName } from "../labels";
import type { AccessData, AccessReq, Role } from "../types";
import { Card, Empty, Icon, Loading, PageHead, Pill, Switch, Tabs, Who, act, ago, dialog, fmtDate, fmtPct, toast, useData } from "../ui";

type Tab = "trial" | "collab" | "pending" | "waitlist" | "sources";

export function AccessPage({ me }: PageProps) {
  const [tab, setTab] = useState<Tab>(() => (new URLSearchParams(location.search).get("tab") as Tab) || "trial");
  const { data, error, set } = useData<AccessData>("/api/admin/access");
  const [inviting, setInviting] = useState(false);
  const owner = me.role === "owner";
  const done = (d: AccessData, what: string) => {
    set(d);
    if (d.link && !d.mailed) {
      // the mail did not go out: show the link so it can be sent by hand
      void dialog({ title: t("邮件没发出去"), body: <LinkBox link={d.link} error={d.mail_error} />, ok: t("知道了") });
    } else toast(what);
  };
  return (
    <>
      <PageHead
        title={t("邀请与申请")}
        sub={t("beta 是邀请制，每个新人都由你批准。")}
        actions={
          <button type="button" className="a-btn pri" onClick={() => setInviting(true)} data-testid="invite-open">
            <Icon name="plus" />
            {t("发邀请")}
          </button>
        }
      />
      {!data ? (
        <Loading error={error} />
      ) : (
        <>
          <Seats data={data} set={set} owner={owner} />
          <Approval data={data} set={set} owner={owner} />
          <Tabs<Tab>
            value={tab}
            onChange={setTab}
            items={[
              { id: "trial", label: t("试用申请"), n: data.trials.length },
              { id: "collab", label: t("搭档申请"), n: data.collabs.length },
              { id: "pending", label: t("待接受的邀请"), n: data.invites.length },
              { id: "waitlist", label: t("等候名单"), n: data.waitlist.length },
              { id: "sources", label: t("来源") },
            ]}
          />
          {tab === "trial" && <Trials rows={data.trials} done={done} sources={data.source_ids} />}
          {tab === "collab" && <Collabs rows={data.collabs} done={done} />}
          {tab === "pending" && <Pending data={data} done={done} me={me} />}
          {tab === "waitlist" && <Trials rows={data.waitlist} done={done} sources={data.source_ids} waitlist />}
          {tab === "sources" && <Sources data={data} />}
        </>
      )}
      {inviting && data && <InviteModal data={data} owner={owner} close={() => setInviting(false)} done={done} />}
    </>
  );
}

function LinkBox({ link, error }: { link: string; error?: string | null }) {
  return (
    <div className="a-stack">
      <p>{t("可以把下面的注册链接复制给对方（7 天内有效）。")}</p>
      {error && <p className="a-muted small">{error}</p>}
      <input className="a-inp mono" readOnly value={link} onFocus={(e) => e.target.select()} aria-label={t("注册链接")} />
    </div>
  );
}

function Seats({ data, set, owner }: { data: AccessData; set: (d: AccessData) => void; owner: boolean }) {
  const { used, total } = data.seats;
  const src = data.sources.reduce((a, s) => ({ invited: a.invited + s.invited, joined: a.joined + s.joined }), { invited: 0, joined: 0 });
  const edit = async () => {
    const v = await dialog({ title: t("beta 名额"), body: t("按节目算：一个新用户建的节目占一个名额，搭档不占。"), ok: t("保存"), input: { label: t("名额"), value: String(total) } });
    if (!v || !/^\d+$/.test(v)) return;
    const out = await act(() => api<AccessData>("PUT", "/api/admin/access/seats", { value: Number(v) }), t("名额已保存"));
    if (out) set(out);
  };
  return (
    <div className="a-grid g4 a-mb">
      <section className="a-card a-kpi">
        <div className="l">
          {t("beta 名额")}
          {owner && (
            <button type="button" className="a-btn ghost sm" onClick={edit} data-testid="seats-edit">
              {t("修改")}
            </button>
          )}
        </div>
        <div className="v" data-testid="seats">
          {used} / {total}
        </div>
        <div className="d mu">{t("按节目算")}</div>
        <div className={`a-bar ${used >= total ? "bad" : used / total >= 0.8 ? "warn" : ""}`}>
          <i style={{ width: `${Math.min(100, (used / Math.max(1, total)) * 100)}%` }} />
        </div>
      </section>
      <section className="a-card a-kpi">
        <div className="l">{t("邀请 → 注册")}</div>
        <div className="v">{src.invited ? fmtPct(src.joined / src.invited) : "—"}</div>
        <div className="d mu">
          {src.joined} / {src.invited}
        </div>
      </section>
      <section className="a-card a-kpi">
        <div className="l">{t("待接受的邀请")}</div>
        <div className="v">{data.invites.length}</div>
        <div className="d mu">{t("7 天内有效")}</div>
      </section>
      <section className="a-card a-kpi">
        <div className="l">{t("等候名单")}</div>
        <div className="v">{data.waitlist.length}</div>
        <div className="d mu">{t("名额满后进来的")}</div>
      </section>
    </div>
  );
}

function Approval({ data, set, owner }: { data: AccessData; set: (d: AccessData) => void; owner: boolean }) {
  const flip = async (on: boolean) => {
    let confirm = "";
    if (!on) {
      const typed = await dialog({
        title: t("关掉「新成员需站长批准」？"),
        body: t("关掉以后，任何节目管理员都能直接邀请新人进来。这一般在正式上线时才做。"),
        ok: t("关掉"),
        danger: true,
        typed: t("关掉批准"),
      });
      if (typed === null) return;
      confirm = typed;
    }
    const out = await act(() => api<AccessData>("PUT", "/api/admin/access/approval", { on, confirm }), on ? t("已打开：新成员要你批准") : t("已关掉"));
    if (out) set(out);
  };
  return (
    <div className="a-card a-strip a-mb">
      <b>{t("新成员需站长批准")}</b>
      <span className="a-muted small">{t("beta 期间开着。关掉以后，节目管理员可以直接邀请搭档。关掉要输入确认。")}</span>
      <span className="spacer" />
      <Switch on={data.approval} onChange={flip} label={t("新成员需站长批准")} disabled={!owner} testid="approval" />
    </div>
  );
}

function Trials({ rows, done, sources, waitlist }: { rows: AccessReq[]; done: (d: AccessData, what: string) => void; sources: string[]; waitlist?: boolean }) {
  if (!rows.length)
    return (
      <Card>
        {waitlist ? (
          <Empty icon="hand" title={t("等候名单是空的")} sub={t("名额满的时候，可以把试用申请先放进等候名单。")} />
        ) : (
          <Empty icon="hand" title={t("没有试用申请")} sub={t("Cloudflare 门禁关掉以后，登录页的「申请试用」会开始有人提交。")} />
        )}
      </Card>
    );
  return (
    <Card pad={false}>
      <div className="a-tw">
        <table className="a-t a-t-cards">
          <thead>
            <tr>
              <th>{t("邮箱")}</th>
              <th>{t("节目名")}</th>
              <th>{t("怎么录音")}</th>
              <th>{t("留言")}</th>
              <th>{t("时间")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <RequestRow key={r.id} r={r} done={done} sources={sources} waitlist={waitlist} />
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function RequestRow({ r, done, sources, waitlist }: { r: AccessReq; done: (d: AccessData, what: string) => void; sources: string[]; waitlist?: boolean }) {
  const [source, setSource] = useState("request");
  const decide = async (action: "invite" | "dismiss" | "waitlist") => {
    const what = action === "invite" ? t("邀请已发出") : action === "waitlist" ? t("已放进等候名单") : t("已忽略");
    const out = await act(() => api<AccessData>("POST", `/api/admin/requests/${r.id}`, { action, source, lang: r.lang }));
    if (out) done(out, what);
  };
  return (
    <tr data-testid="trial-row">
      <td className="mono" data-label={t("邮箱")}>
        {r.email}
      </td>
      <td data-label={t("节目名")}>{r.show || "—"}</td>
      <td data-label={t("怎么录音")}>{r.tracks ? <Pill tone={r.tracks === "mixed" ? "warn" : ""}>{TRACKS[r.tracks]?.() ?? r.tracks}</Pill> : "—"}</td>
      <td className="wrap a-muted" data-label={t("留言")}>
        {r.note || "—"}
      </td>
      <td className="a-muted" data-label={t("时间")}>
        {ago(r.created)}
      </td>
      <td>
        <div className="a-row end">
          <select className="a-inp sm" value={source} onChange={(e) => setSource(e.target.value)} aria-label={t("来源")}>
            {sources.map((s) => (
              <option key={s} value={s}>
                {sourceName(s)}
              </option>
            ))}
          </select>
          <button type="button" className="a-btn sm" onClick={() => decide("dismiss")}>
            {t("忽略")}
          </button>
          {!waitlist && (
            <button type="button" className="a-btn sm" onClick={() => decide("waitlist")}>
              {t("进等候名单")}
            </button>
          )}
          <button type="button" className="a-btn sm acc" onClick={() => decide("invite")} data-testid="trial-invite">
            {t("邀请")}
          </button>
        </div>
      </td>
    </tr>
  );
}

function Collabs({ rows, done }: { rows: AccessReq[]; done: (d: AccessData, what: string) => void }) {
  if (!rows.length)
    return (
      <Card>
        <Empty icon="users" title={t("没有搭档申请")} sub={t("节目管理员想拉没账号的人进来时，申请会出现在这里。")} />
      </Card>
    );
  const decide = async (r: AccessReq, action: "invite" | "dismiss") => {
    const out = await act(() => api<AccessData>("POST", `/api/admin/requests/${r.id}`, { action, lang: r.lang }));
    if (out) done(out, action === "invite" ? t("已发出注册链接") : t("已拒绝，已告诉申请的人"));
  };
  return (
    <Card pad={false}>
      <div className="a-tw">
        <table className="a-t a-t-cards">
          <thead>
            <tr>
              <th>{t("谁申请")}</th>
              <th>{t("想拉进来的人")}</th>
              <th>{t("节目")}</th>
              <th>{t("时间")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} data-testid="collab-row">
                <td data-label={t("谁申请")}>
                  <Who email={r.by} name={r.by_name} />
                </td>
                <td className="mono" data-label={t("想拉进来的人")}>
                  {r.email}
                </td>
                <td data-label={t("节目")}>{r.show}</td>
                <td className="a-muted" data-label={t("时间")}>
                  {ago(r.created)}
                </td>
                <td>
                  <div className="a-row end">
                    <button type="button" className="a-btn sm" onClick={() => decide(r, "dismiss")}>
                      {t("拒绝")}
                    </button>
                    <button type="button" className="a-btn sm acc" onClick={() => decide(r, "invite")} data-testid="collab-invite">
                      {t("批准并邀请")}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function Pending({ data, done, me }: { data: AccessData; done: (d: AccessData, what: string) => void; me: { role: Role } }) {
  if (!data.invites.length)
    return (
      <Card>
        <Empty icon="mail" title={t("没有待接受的邀请")} sub={t("发出的邀请 7 天内有效。")} />
      </Card>
    );
  const resend = async (id: string) => {
    const out = await act(() => api<AccessData>("POST", `/api/admin/invites/${id}/resend`));
    if (out) done(out, t("邀请已重新发出"));
  };
  const revoke = async (id: string, email: string) => {
    const ok = await dialog({ title: t("撤回邀请？"), body: t("{email} 收到的链接会马上失效。", { email }), ok: t("撤回"), danger: true });
    if (ok === null) return;
    const out = await act(() => api<AccessData>("DELETE", `/api/admin/invites/${id}`));
    if (out) done(out, t("邀请已撤回"));
  };
  return (
    <Card pad={false}>
      <div className="a-tw">
        <table className="a-t a-t-cards">
          <thead>
            <tr>
              <th>{t("邮箱")}</th>
              <th>{t("角色")}</th>
              <th>{t("套餐")}</th>
              <th>{t("来源")}</th>
              <th>{t("发出")}</th>
              <th>{t("到期")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data.invites.map((i) => (
              <tr key={i.id} data-testid="invite-row">
                <td className="mono" data-label={t("邮箱")}>
                  {i.email}
                </td>
                <td data-label={t("角色")}>{ROLE[i.role]?.()}</td>
                <td data-label={t("套餐")}>{planName(i.plan)}</td>
                <td data-label={t("来源")}>{i.source ? <Pill>{sourceName(i.source)}</Pill> : "—"}</td>
                <td className="a-muted" data-label={t("发出")}>
                  {ago(i.created)}
                </td>
                <td className="a-muted" data-label={t("到期")}>
                  {fmtDate(i.exp)}
                </td>
                <td>
                  <div className="a-row end">
                    {(me.role === "owner" || i.role === "member") && (
                      <button type="button" className="a-btn sm" onClick={() => resend(i.id)}>
                        {t("重新发送")}
                      </button>
                    )}
                    <button type="button" className="a-btn sm danger" onClick={() => revoke(i.id, i.email)} data-testid="invite-revoke">
                      {t("撤回")}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function Sources({ data }: { data: AccessData }) {
  return (
    <div className="a-grid g-21">
      <Card title={t("各来源的人留不留得住")} pad={false}>
        {data.sources.length ? (
          <table className="a-t">
            <thead>
              <tr>
                <th>{t("来源")}</th>
                <th className="n">{t("邀请")}</th>
                <th className="n">{t("注册")}</th>
                <th className="n">{t("第 4 周还在")}</th>
              </tr>
            </thead>
            <tbody>
              {data.sources.map((s) => (
                <tr key={s.source}>
                  <td>{sourceName(s.source)}</td>
                  <td className="n">{s.invited}</td>
                  <td className="n">{s.joined}</td>
                  <td className="n">{s.joined ? fmtPct(s.week4 / s.joined) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <Empty icon="chart" title={t("还没有来源数据")} sub={t("发邀请时选一个来源，以后就能在这里比较。")} />
        )}
      </Card>
      <Card title={t("说明")}>
        <p className="a-muted">{t("发邀请时选一个来源（小宇宙、朋友介绍、问卷……）。几周以后就能看出哪个渠道的人真正在用。「第 4 周还在」= 注册满 4 周、第 4 周还打开过 LACUNA。")}</p>
      </Card>
    </div>
  );
}

function InviteModal({ data, owner, close, done }: { data: AccessData; owner: boolean; close: () => void; done: (d: AccessData, what: string) => void }) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("member");
  const [source, setSource] = useState("friend");
  const [plan, setPlan] = useState("basic");
  const [lang, setLang] = useState<"zh" | "en">("zh");
  const [busy, setBusy] = useState(false);
  const full = data.seats.used >= data.seats.total;
  const send = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    const out = await act(() => api<AccessData>("POST", "/api/admin/invites", { email, role, source, plan, lang }));
    setBusy(false);
    if (out) {
      close();
      done(out, t("邀请已发出"));
    }
  };
  return (
    <div className="a-scrim center" onMouseDown={(e) => e.target === e.currentTarget && close()}>
      <form className="a-modal" role="dialog" aria-modal="true" aria-label={t("发邀请")} onSubmit={send} data-testid="invite-modal">
        <h3>{t("发邀请")}</h3>
        {full && (
          <div className="a-alert warn small">
            <Icon name="users" />
            <span>{t("beta 名额已满（{u} / {n}）。还可以发，但会超出名额。", { u: data.seats.used, n: data.seats.total })}</span>
          </div>
        )}
        <label className="a-lbl">
          {t("邮箱")}
          <input className="a-inp" type="email" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@example.com" data-testid="invite-email" />
        </label>
        <div className="a-grid g2">
          <label className="a-lbl">
            {t("角色")}
            <select className="a-inp" value={role} onChange={(e) => setRole(e.target.value as Role)}>
              <option value="member">{ROLE.member()}</option>
              {owner && <option value="admin">{ROLE.admin()}</option>}
            </select>
          </label>
          <label className="a-lbl">
            {t("来源")}
            <select className="a-inp" value={source} onChange={(e) => setSource(e.target.value)} data-testid="invite-source">
              {data.source_ids.map((s) => (
                <option key={s} value={s}>
                  {sourceName(s)}
                </option>
              ))}
            </select>
          </label>
          <label className="a-lbl">
            {t("套餐")}
            <select className="a-inp" value={plan} onChange={(e) => setPlan(e.target.value)}>
              {["trial", "basic", "pro"].map((p) => (
                <option key={p} value={p}>
                  {planName(p)}
                </option>
              ))}
            </select>
          </label>
          <label className="a-lbl">
            {t("邮件语言")}
            <select className="a-inp" value={lang} onChange={(e) => setLang(e.target.value as "zh" | "en")}>
              <option value="zh">{t("中文")}</option>
              <option value="en">English</option>
            </select>
          </label>
        </div>
        <p className="a-muted small">{t("对方会收到注册链接，7 天内有效。注册后会有一个自己的新节目。")}</p>
        <div className="a-row end">
          <button type="button" className="a-btn" onClick={close}>
            {t("取消")}
          </button>
          <button type="submit" className="a-btn pri" disabled={busy || !email} data-testid="invite-send">
            {t("发送")}
          </button>
        </div>
      </form>
    </div>
  );
}
