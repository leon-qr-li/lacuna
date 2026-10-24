// 用户: every account with filters and search; a click opens the drawer on the right with the account, shows,
// activity, sign-ins, notes, hour requests and feedback, and the actions (each change is in the audit log;
// the dangerous ones ask for the code again, 立即彻底删除 also for the typed email).
import { useCallback, useMemo, useState } from "react";
import { api } from "../api";
import type { PageProps } from "../Shell";
import { t } from "../i18n";
import { FB_STATUS, ROLE, eventName, planName, sourceName } from "../labels";
import type { Me, Note, PlanLimits, UserDetail, UserRow } from "../types";
import { Avatar, Card, Chips, Drawer, Empty, Loading, PageHead, Pill, Who, act, ago, dialog, fmtBytes, fmtDate, fmtNum, fmtTime, fmtUsd, isDemo, toast, useData } from "../ui";

type Filter = "all" | "active" | "silent" | "near" | "staff" | "disabled" | "no2fa";
const DAY = 86400;

export function UsersPage({ me }: PageProps) {
  const { data, error, reload } = useData<{ users: UserRow[]; plans: PlanLimits[] }>("/api/admin/users");
  const [filter, setFilter] = useState<Filter>("all");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<string | null>(() => new URLSearchParams(location.search).get("u"));
  const now = Date.now() / 1000;
  const rows = useMemo(() => {
    if (!data) return [];
    const s = q.trim().toLowerCase();
    return data.users.filter((u) => {
      const keep =
        filter === "all" ||
        (filter === "active" && u.last !== null && now - u.last < 7 * DAY) ||
        (filter === "silent" && u.silent) ||
        (filter === "near" && u.hours_used !== null && u.hours !== null && u.hours_used / u.hours >= 0.8) ||
        (filter === "staff" && u.role !== "member") ||
        (filter === "disabled" && u.disabled) ||
        (filter === "no2fa" && !u.twofa);
      return keep && (!s || u.email.includes(s) || (u.name || "").toLowerCase().includes(s));
    });
  }, [data, filter, q, now]);
  const close = useCallback(() => setOpen(null), []);
  return (
    <>
      <PageHead title={t("用户")} sub={data ? t("{n} 个账号", { n: data.users.length }) : undefined} />
      <div className="a-filters">
        <Chips<Filter>
          value={filter}
          onChange={setFilter}
          items={[
            { id: "all", label: t("全部") },
            { id: "active", label: t("最近 7 天活跃") },
            { id: "silent", label: t("沉默 14 天") },
            { id: "near", label: t("额度快用完") },
            { id: "staff", label: t("站长和管理员") },
            { id: "disabled", label: t("已停用") },
            { id: "no2fa", label: t("没开两步验证") },
          ]}
        />
        <span className="spacer" />
        <input className="a-inp" type="search" placeholder={t("搜索邮箱、名字")} value={q} onChange={(e) => setQ(e.target.value)} aria-label={t("搜索")} data-testid="user-search" />
      </div>
      {!data ? (
        <Loading error={error} />
      ) : !rows.length ? (
        <Card>
          <Empty icon="users" title={t("没有符合的账号")} />
        </Card>
      ) : (
        <Card pad={false}>
          <div className="a-tw">
            <table className="a-t a-t-cards">
              <thead>
                <tr>
                  <th>{t("用户")}</th>
                  <th>{t("角色")}</th>
                  <th>{t("套餐")}</th>
                  <th className="n">{t("节目")}</th>
                  <th className="n">{t("剧集")}</th>
                  <th className="n">{t("AI 花费")}</th>
                  <th className="n">{t("占用空间")}</th>
                  <th>{t("最近活跃")}</th>
                  <th>{t("来源")}</th>
                  <th>{t("状态")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((u) => (
                  <tr key={u.email} className="click" onClick={() => setOpen(u.email)} data-testid="user-row">
                    <td>
                      <Who email={u.email} name={u.name} sub={u.email} />
                    </td>
                    <td data-label={t("角色")}>{u.role === "owner" ? <Pill tone="acc">{ROLE.owner()}</Pill> : u.role === "admin" ? <Pill tone="info">{ROLE.admin()}</Pill> : ROLE.member()}</td>
                    <td data-label={t("套餐")}>
                      {planName(u.plan)}
                      {u.free && <span className="a-muted small"> · {t("免费")}</span>}
                    </td>
                    <td className="n" data-label={t("节目")}>
                      {u.shows}
                    </td>
                    <td className="n" data-label={t("剧集")}>
                      {u.episodes}
                    </td>
                    <td className="n" data-label={t("AI 花费")}>
                      {fmtUsd(u.ai)}
                    </td>
                    <td className="n" data-label={t("占用空间")}>
                      {fmtBytes(u.size)}
                    </td>
                    <td data-label={t("最近活跃")}>
                      <span className={u.silent ? "" : "a-muted"}>{u.last ? ago(u.last) : t("还没来过")}</span> {u.silent && <Pill tone="warn">{t("沉默")}</Pill>}
                    </td>
                    <td className="a-muted" data-label={t("来源")}>
                      {sourceName(u.source)}
                    </td>
                    <td data-label={t("状态")}>
                      {u.disabled ? <Pill tone="bad">{t("已停用")}</Pill> : <Pill tone="ok">{t("正常")}</Pill>}
                      {!u.twofa && <Pill tone="warn">{t("没开两步验证")}</Pill>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      {open && <UserDrawer email={open} me={me} plans={data?.plans ?? []} close={close} changed={reload} />}
    </>
  );
}

export function UserDrawer({ email, me, plans, close, changed }: { email: string; me: Me; plans: PlanLimits[]; close: () => void; changed?: () => void }) {
  const url = `/api/admin/users/${encodeURIComponent(email)}`;
  const { data: d, error, set } = useData<UserDetail>(url);
  const owner = me.role === "owner";
  const self = email === me.email;
  const update = async (body: Record<string, unknown>, done: string) => {
    const out = await act(() => api<UserDetail>("POST", url, body), done);
    if (out) {
      set(out);
      changed?.();
    }
  };
  if (!d)
    return (
      <Drawer title={email} onClose={close}>
        <Loading error={error} />
      </Drawer>
    );
  const u = d.user;
  const mail = async () => {
    const subject = await dialog({ title: t("发邮件给 {who}", { who: u.name || u.email }), ok: t("下一步"), input: { label: t("主题"), value: t("关于你的 LACUNA 账号") } });
    if (!subject) return;
    const text = await dialog({
      title: t("发邮件给 {who}", { who: u.name || u.email }),
      body: t("从 LACUNA 的发信地址发出，对方回复会到你的邮箱。"),
      ok: t("发送"),
      input: { label: t("正文"), multiline: true },
    });
    if (text) await act(() => api("POST", `${url}/mail`, { subject, text }), t("邮件已发出"));
  };
  const hours = async () => {
    const n = await dialog({ title: t("给 {who} 加时长", { who: u.name || u.email }), body: t("只加这个月。会记在「时长申请 → 处理过的」里。"), ok: t("加"), input: { label: t("小时"), value: "1" } });
    if (!n || !(Number(n) > 0)) return;
    const out = await act(() => api<UserDetail>("POST", `${url}/hours`, { hours: Number(n) }), t("已加 {n} 小时", { n }));
    if (out) set(out);
  };
  const endSessions = async () => {
    const ok = await dialog({ title: t("退出对方所有登录？"), body: t("{who} 在所有设备上都要重新登录。", { who: u.name || u.email }), ok: t("全部退出") });
    if (ok === null) return;
    const out = await act(() => api<UserDetail>("POST", `${url}/sessions/end`), t("已退出对方所有登录"));
    if (out) set(out);
  };
  const remove = async () => {
    const ok = await dialog({
      title: t("删除这个账号？"),
      body: t("账号会被删除，对方看到的是「永久删除」。60 天内你可以在回收区恢复。"),
      ok: t("删除账号"),
      danger: true,
      typed: u.email,
    });
    if (ok === null) return;
    const out = await act(() => api("DELETE", url), t("账号已删除，进了回收区"));
    if (out) {
      changed?.();
      close();
    }
  };
  const erase = async () => {
    const typed = await dialog({
      title: t("立即彻底删除？"),
      body: t("跳过 60 天：账号和只有 TA 一个人的节目（包括音频）马上清除，不能恢复。"),
      ok: t("立即彻底删除"),
      danger: true,
      typed: u.email,
    });
    if (typed === null) return;
    const out = await act(() => api<{ shows: number }>("POST", `${url}/erase`, { confirm: typed }));
    if (out) {
      toast(t("已彻底删除，连同 {n} 个节目", { n: out.shows }));
      changed?.();
      close();
    }
  };
  return (
    <Drawer
      title={u.name || u.email}
      onClose={close}
      head={
        <>
          <Avatar name={u.name || u.email} big />
          <div className="a-grow">
            <h3>{u.name || u.email}</h3>
            <div className="a-muted small">
              {u.email}
              {u.lang ? ` · ${u.lang === "en" ? "English" : t("中文")}` : ""}
            </div>
          </div>
        </>
      }
    >
      <div className="a-grid g3">
        <Mini label={t("剧集")} value={fmtNum(u.episodes)} />
        <Mini label={t("本月用量")} value={u.hours_used === null ? "—" : `${fmtNum(u.hours_used, 1)} / ${u.hours ?? "∞"} h`} />
        <Mini label={t("AI 花费")} value={fmtUsd(u.ai)} />
      </div>
      <section>
        <h4>{t("账号")}</h4>
        <dl className="a-kv">
          <dt>{t("角色")}</dt>
          <dd className="a-row wrap">
            {u.role === "owner" ? (
              <Pill tone="acc">{ROLE.owner()}</Pill>
            ) : (
              <select className="a-inp sm" value={u.role} disabled={!owner || self} onChange={(e) => update({ role: e.target.value }, t("角色已改"))} aria-label={t("角色")} data-testid="user-role">
                <option value="member">{ROLE.member()}</option>
                <option value="admin">{ROLE.admin()}</option>
              </select>
            )}
            {!owner && <span className="a-muted small">{t("只有站长能改")}</span>}
          </dd>
          <dt>{t("套餐")}</dt>
          <dd className="a-row wrap">
            <select className="a-inp sm" value={u.plan} disabled={u.role !== "member"} onChange={(e) => update({ plan: e.target.value }, t("套餐已改"))} aria-label={t("套餐")} data-testid="user-plan">
              {(plans.length ? plans.map((p) => p.id) : ["trial", "basic", "pro"]).map((p) => (
                <option key={p} value={p}>
                  {planName(p)}
                </option>
              ))}
            </select>
            {d.bonus_hours > 0 && <Pill tone="ok">{t("额外 +{n} 小时", { n: fmtNum(d.bonus_hours, 1) })}</Pill>}
          </dd>
          <dt>{t("注册")}</dt>
          <dd>
            {fmtDate(u.created)} · {t("来源")}：{sourceName(u.source)}
            {u.invited_by ? ` · ${t("邀请人")}：${u.invited_by}` : ""}
          </dd>
          <dt>{t("两步验证")}</dt>
          <dd>{u.twofa ? <Pill tone="ok">{t("已开启")}</Pill> : <Pill tone="warn">{t("没开")}</Pill>}</dd>
          <dt>{t("记住的设备")}</dt>
          <dd>{d.devices}</dd>
          <dt>{t("状态")}</dt>
          <dd>{u.disabled ? <Pill tone="bad">{t("已停用")}</Pill> : <Pill tone="ok">{t("正常")}</Pill>}</dd>
        </dl>
      </section>
      <section>
        <h4>{t("节目")}</h4>
        {d.shows.length ? (
          <table className="a-t">
            <tbody>
              {d.shows.map((s) => (
                <tr key={s.id}>
                  <td>
                    {s.name}
                    {s.sample && <span className="a-muted small"> · {t("示例")}</span>}
                    {s.archived && <span className="a-muted small"> · {t("已归档")}</span>}
                  </td>
                  <td className="a-muted">{s.role}</td>
                  <td className="n">{t("{n} 集", { n: s.episodes ?? 0 })}</td>
                  <td>
                    <OpenShow sid={s.id} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="a-muted small">{t("没有节目")}</p>
        )}
      </section>
      <UserNotes email={u.email} notes={d.notes} />
      <section>
        <h4>{t("活动记录")}</h4>
        {d.activity.length ? (
          <div className="a-tl">
            {d.activity.slice(0, 30).map((a, i) => (
              <div key={i}>
                <time>{fmtTime(a.ts)}</time>
                {eventName(a.ev)}
                {a.show ? ` · ${a.show}` : ""}
                {a.ep ? ` · ${a.ep}` : ""}
              </div>
            ))}
          </div>
        ) : (
          <p className="a-muted small">{t("还没有活动")}</p>
        )}
      </section>
      <section>
        <h4>{t("在哪些设备登录着")}</h4>
        {d.sessions.length ? (
          <table className="a-t">
            <tbody>
              {d.sessions.map((s, i) => (
                <tr key={i}>
                  <td>{s.device}</td>
                  <td className="a-muted">{t("最近 {t}", { t: ago(s.seen) })}</td>
                  <td className="a-muted">{t("登录于 {d}", { d: fmtDate(s.created) })}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="a-muted small">{t("现在没有登录")}</p>
        )}
      </section>
      {d.feedback.length > 0 && (
        <section>
          <h4>{t("TA 的反馈")}</h4>
          <div className="a-stack">
            {d.feedback.slice(0, 5).map((f) => (
              <div key={f.id} className="a-mini-fb">
                <Pill tone={FB_STATUS[f.status].tone}>{FB_STATUS[f.status].label()}</Pill>
                <span className="a-clip">{f.text}</span>
                <span className="a-muted small">{ago(f.created)}</span>
              </div>
            ))}
          </div>
        </section>
      )}
      {d.hours.length > 0 && (
        <section>
          <h4>{t("时长申请")}</h4>
          <table className="a-t">
            <tbody>
              {d.hours.map((h) => (
                <tr key={h.id}>
                  <td>{fmtDate(h.created)}</td>
                  <td>{h.status === "approved" ? <Pill tone="ok">{t("批准")}</Pill> : h.status === "declined" ? <Pill>{t("拒绝")}</Pill> : <Pill tone="acc">{t("待批")}</Pill>}</td>
                  <td className="n">{fmtNum(h.status === "approved" ? h.granted ?? h.hours : h.hours, 1)} h</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
      <section>
        <h4>{t("操作")}</h4>
        <div className="a-row wrap">
          <button type="button" className="a-btn" onClick={mail} data-testid="user-mail">
            {t("发邮件")}
          </button>
          {owner && (
            <button type="button" className="a-btn" onClick={hours} data-testid="user-hours">
              {t("加时长")}
            </button>
          )}
          {!self && u.twofa && (
            <button type="button" className="a-btn" onClick={() => update({ reset_2fa: true }, t("两步验证已重置"))}>
              {t("重置两步验证")}
            </button>
          )}
          {!self && (
            <button type="button" className="a-btn" onClick={endSessions}>
              {t("退出对方所有登录")}
            </button>
          )}
          {!self && u.role !== "owner" && (
            <button type="button" className="a-btn" onClick={() => update({ disabled: !u.disabled }, u.disabled ? t("已恢复使用") : t("已停用"))} data-testid="user-disable">
              {u.disabled ? t("恢复使用") : t("停用")}
            </button>
          )}
          {!self && u.role !== "owner" && (
            <button type="button" className="a-btn danger" onClick={remove} data-testid="user-delete">
              {t("删除账号")}
            </button>
          )}
          {owner && !self && u.role !== "owner" && (
            <button type="button" className="a-btn danger" onClick={erase} data-testid="user-erase">
              {t("立即彻底删除")}
            </button>
          )}
        </div>
        <p className="a-muted small">{t("删除后进回收区 60 天（对方看到的是永久删除）。「立即彻底删除」跳过 60 天，只有站长能做。改动都会再要一次验证码，并记进操作日志。")}</p>
      </section>
    </Drawer>
  );
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div className="a-card a-kpi flat">
      <div className="l">{label}</div>
      <div className="v sm">{value}</div>
    </div>
  );
}

function UserNotes({ email, notes: first }: { email: string; notes: Note[] }) {
  const [notes, setNotes] = useState(first);
  const [text, setText] = useState("");
  const add = async () => {
    const out = await act(() => api<{ notes: Note[] }>("POST", "/api/admin/notes", { target: `user:${email}`, text }), t("备注已保存"));
    if (out) {
      setNotes(out.notes);
      setText("");
    }
  };
  return (
    <section>
      <h4>{t("站长备注")}</h4>
      <div className="a-stack">
        {notes.map((n) => (
          <div key={n.id} className="a-bubble note">
            <div className="who">
              {n.email} · {fmtTime(n.ts)}
            </div>
            {n.text}
          </div>
        ))}
        <textarea className="a-inp" rows={2} maxLength={4000} placeholder={t("这人是谁、从哪来、在做什么节目")} value={text} onChange={(e) => setText(e.target.value)} aria-label={t("站长备注")} data-testid="user-note" />
        <div className="a-row end">
          <button type="button" className="a-btn sm" disabled={!text.trim()} onClick={add}>
            {t("保存备注")}
          </button>
        </div>
      </div>
    </section>
  );
}

/** 打开节目: opens the main site for a look (recorded in the audit log). The main site shows the show only to its members. */
export function OpenShow({ sid }: { sid: string }) {
  const go = async () => {
    if (isDemo()) return toast(t("演示数据，不会保存"));
    const out = await act(() => api<{ url: string }>("POST", `/api/admin/shows/${encodeURIComponent(sid)}/open`));
    if (out) window.open(out.url, "_blank", "noopener,noreferrer");
  };
  return (
    <button type="button" className="a-btn ghost sm" onClick={go} title={t("打开主站（会记日志）")}>
      {t("打开 ↗")}
    </button>
  );
}
