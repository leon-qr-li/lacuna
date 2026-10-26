// 系统设置: 通用 (system terms, mail, the AI key's status, sign-in protection, the daily digest and the AI budget),
// 公告与维护 (the notice bar on the main site; maintenance pauses new uploads and imports), and 后台成员与安全
// (who can enter the admin, this account's admin sign-ins, the security rules that were decided).
import { useState } from "react";
import { api } from "../api";
import type { PageProps } from "../Shell";
import { t } from "../i18n";
import { ROLE } from "../labels";
import type { SettingsData } from "../types";
import { Card, Loading, PageHead, Pill, Switch, Tabs, Who, act, ago, dialog, fmtTime, fmtUsd, useData } from "../ui";

type Tab = "general" | "notice" | "staff";

export function SettingsPage({ me, go }: PageProps) {
  const [tab, setTab] = useState<Tab>("general");
  const { data, error, set } = useData<SettingsData>("/api/admin/settings");
  const owner = me.role === "owner";
  return (
    <>
      <PageHead title={t("系统设置")} />
      <Tabs<Tab>
        value={tab}
        onChange={setTab}
        items={[
          { id: "general", label: t("通用") },
          { id: "notice", label: t("公告与维护") },
          { id: "staff", label: t("后台成员与安全") },
        ]}
      />
      {!data ? (
        <Loading error={error} />
      ) : tab === "general" ? (
        <General s={data} set={set} go={go} />
      ) : tab === "notice" ? (
        <Notice s={data} set={set} owner={owner} />
      ) : (
        <Staff s={data} set={set} owner={owner} me={me.email} />
      )}
    </>
  );
}

function General({ s, set, go }: { s: SettingsData; set: (d: SettingsData) => void; go: (p: string) => void }) {
  const [term, setTerm] = useState("");
  const saveTerms = async (terms: string[]) => {
    const out = await act(() => api<SettingsData>("PUT", "/api/admin/settings/terms", { terms }), t("专有名词已保存"));
    if (out) set(out);
  };
  const testMail = () => act(() => api("POST", "/api/admin/settings/test-mail"), t("测试信已发到你的邮箱"));
  return (
    <div className="a-grid g2">
      <Card title={t("系统专有名词")} sub={t("{n} 个", { n: s.terms.length })}>
        <p className="a-muted small">{t("全站通用的专有名词，语音识别和 LACUNA 都会参考。每个节目自己的词在节目设置里。")}</p>
        <div className="a-ctx">
          {s.terms.map((x) => (
            <span key={x} className="a-pill">
              {x}
              <button type="button" className="a-x" aria-label={t("去掉 {x}", { x })} onClick={() => saveTerms(s.terms.filter((y) => y !== x))}>
                ×
              </button>
            </span>
          ))}
        </div>
        <form
          className="a-row a-mt"
          onSubmit={(e) => {
            e.preventDefault();
            if (term.trim() && !s.terms.includes(term.trim())) saveTerms([...s.terms, term.trim()]).then(() => setTerm(""));
          }}
        >
          <input className="a-inp a-grow" placeholder={t("加一个词")} value={term} maxLength={40} onChange={(e) => setTerm(e.target.value)} aria-label={t("加一个词")} data-testid="term-input" />
          <button type="submit" className="a-btn" disabled={!term.trim()}>
            {t("加")}
          </button>
        </form>
      </Card>
      <Card title={t("邮件")}>
        <dl className="a-kv">
          <dt>{t("发信服务")}</dt>
          <dd>{s.mail.configured ? <Pill tone="ok">{t("正常")}</Pill> : <Pill tone="bad">{t("没配置")}</Pill>}</dd>
          <dt>{t("发件地址")}</dt>
          <dd className="mono">{s.mail.sender}</dd>
          <dt>{t("每日汇总")}</dt>
          <dd>
            {t("每天 {h}:00（温哥华时间）", { h: s.digest.hour })}
            {s.digest.last && <span className="a-muted small"> · {t("上次 {d}", { d: s.digest.last })}</span>}
          </dd>
        </dl>
        <button type="button" className="a-btn a-mt" onClick={testMail} disabled={!s.mail.configured} data-testid="test-mail">
          {t("发一封测试信")}
        </button>
      </Card>
      <Card title={t("LACUNA 密钥")}>
        <dl className="a-kv">
          <dt>{t("状态")}</dt>
          <dd>{s.key.present ? <Pill tone="ok">{t("正常")}</Pill> : <Pill tone="bad">{t("没找到")}</Pill>}</dd>
          <dt>{t("来源")}</dt>
          <dd className="a-muted">{s.key.present ? t("服务器环境变量，后台不显示密钥本身") : "—"}</dd>
          <dt>{t("AI 月度预算")}</dt>
          <dd>
            {fmtUsd(s.budget, 0)}{" "}
            <button type="button" className="a-btn ghost sm" onClick={() => go("/ai")}>
              {t("去改 →")}
            </button>
          </dd>
        </dl>
      </Card>
      <Card title={t("登录保护")}>
        <dl className="a-kv">
          <dt>{t("登录页防机器人")}</dt>
          <dd>{s.turnstile ? <Pill tone="ok">{t("开着")}</Pill> : <Pill>{t("关（门禁还开着）")}</Pill>}</dd>
          <dt>{t("主站门禁")}</dt>
          <dd>
            {s.access === null ? (
              <span className="a-muted">{t("本地开发，没有门禁")}</span>
            ) : s.access ? (
              <>
                <Pill tone="ok">{t("开着")}</Pill> <span className="a-muted small">{t("关掉要你输入「关掉 Access」")}</span>
              </>
            ) : (
              <Pill tone="warn">{t("关着")}</Pill>
            )}
          </dd>
          <dt>{t("后台门禁")}</dt>
          <dd>{s.cloud ? <Pill tone="ok">{t("永远开着")}</Pill> : <span className="a-muted">{t("本地开发，没有门禁")}</span>}</dd>
        </dl>
      </Card>
    </div>
  );
}

function Notice({ s, set, owner }: { s: SettingsData; set: (d: SettingsData) => void; owner: boolean }) {
  const [zh, setZh] = useState(s.notice.zh);
  const [en, setEn] = useState(s.notice.en);
  const [until, setUntil] = useState(s.notice.until ?? "");
  const save = async (on: boolean) => {
    const out = await act(() => api<SettingsData>("PUT", "/api/admin/settings/notice", { on, zh, en, until: until || null }), on ? t("公告已挂上") : t("公告已撤下"));
    if (out) set(out);
  };
  const maintenance = async (on: boolean) => {
    if (on) {
      const ok = await dialog({
        title: t("开维护模式？"),
        body: t("新的上传和导入会暂停，已经在跑的会跑完。用户看到「正在维护，几分钟后再试」。记得做完关掉。"),
        ok: t("开维护模式"),
      });
      if (ok === null) return;
    }
    const out = await act(() => api<SettingsData>("PUT", "/api/admin/settings/maintenance", { on }), on ? t("维护模式已开") : t("维护模式已关"));
    if (out) set(out);
  };
  return (
    <div className="a-grid g2">
      <Card title={t("站内公告")} right={s.notice.on ? <Pill tone="ok">{t("挂着")}</Pill> : <Pill>{t("没挂")}</Pill>}>
        <p className="a-muted small">{t("显示在主站底部，用户可以关掉。按用户的界面语言显示。")}</p>
        <label className="a-lbl">
          {t("中文")}
          <textarea className="a-inp" rows={2} maxLength={300} value={zh} onChange={(e) => setZh(e.target.value)} data-testid="notice-zh" />
        </label>
        <label className="a-lbl">
          English
          <textarea className="a-inp" rows={2} maxLength={300} value={en} onChange={(e) => setEn(e.target.value)} data-testid="notice-en" />
        </label>
        <div className="a-row wrap a-mt">
          <label className="a-row small">
            {t("显示到")}
            <input className="a-inp sm" type="date" value={until} onChange={(e) => setUntil(e.target.value)} aria-label={t("显示到")} />
          </label>
          <span className="spacer" />
          {s.notice.on && (
            <button type="button" className="a-btn" onClick={() => save(false)} data-testid="notice-off">
              {t("撤下")}
            </button>
          )}
          <button type="button" className="a-btn pri" disabled={!zh.trim() && !en.trim()} onClick={() => save(true)} data-testid="notice-on">
            {s.notice.on ? t("更新") : t("挂上")}
          </button>
        </div>
      </Card>
      <Card title={t("维护模式")}>
        <p className="a-muted small">{t("暂停新的上传和导入，已经在跑的跑完。用户看到「正在维护，几分钟后再试」。只有站长能开关，要再输一次验证码。")}</p>
        <div className="a-row a-mt">
          <b className="a-w5">{t("暂停新任务")}</b>
          <span className="spacer" />
          <Switch on={s.maintenance.on} onChange={maintenance} label={t("维护模式")} disabled={!owner} testid="maintenance" />
        </div>
      </Card>
    </div>
  );
}

function Staff({ s, set, owner, me }: { s: SettingsData; set: (d: SettingsData) => void; owner: boolean; me: string }) {
  const role = async (email: string, r: "admin" | "member") => {
    const out = await act(() => api<SettingsData>("PUT", `/api/admin/settings/staff/${encodeURIComponent(email)}`, { role: r }), r === "admin" ? t("已设为管理员") : t("已取消管理员"));
    if (out) set(out);
  };
  const add = async () => {
    const email = await dialog({
      title: t("加管理员"),
      body: t("对方要先有 LACUNA 账号并开了两步验证。还要把 TA 的邮箱加进后台的 Cloudflare 门禁名单，否则进不来。"),
      ok: t("设为管理员"),
      input: { label: t("邮箱") },
    });
    if (email) await role(email.trim().toLowerCase(), "admin");
  };
  const endSession = async (id: string | null) => {
    const out = await act(() => api<{ sessions: SettingsData["sessions"] }>("POST", "/api/admin/auth/sessions/end", { id }), t("已退出"));
    if (out) set({ ...s, sessions: out.sessions });
  };
  const rules: [string, string][] = [
    [t("后台门禁"), t("永远开着，只有名单上的人能打开")],
    [t("后台登录有效期"), t("8 小时，不能「记住我」")],
    [t("危险操作"), t("再输验证码（15 分钟内一次）")],
    [t("登录提醒"), t("每次登录后台都给站长发邮件")],
    [t("音频和逐字稿"), t("后台看不到")],
    [t("通行密钥"), t("正式上线前加")],
  ];
  return (
    <div className="a-grid g2">
      <Card
        title={t("谁能进后台")}
        pad={false}
        right={
          owner && (
            <button type="button" className="a-btn sm" onClick={add} data-testid="staff-add">
              {t("加管理员")}
            </button>
          )
        }
      >
        <div className="a-tw">
          <table className="a-t">
            <thead>
              <tr>
                <th>{t("人")}</th>
                <th>{t("角色")}</th>
                <th>{t("两步验证")}</th>
                <th>{t("最近登录后台")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {s.staff.map((x) => (
                <tr key={x.email}>
                  <td>
                    <Who email={x.email} name={x.name} />
                  </td>
                  <td>{x.role === "owner" ? <Pill tone="acc">{ROLE.owner()}</Pill> : <Pill tone="info">{ROLE.admin()}</Pill>}</td>
                  <td>{x.twofa ? <Pill tone="ok">{t("已开启")}</Pill> : <Pill tone="warn">{t("没开，进不了后台")}</Pill>}</td>
                  <td className="a-muted">{x.last_admin ? ago(x.last_admin) : t("从没登录")}</td>
                  <td>
                    {owner && x.role === "admin" && x.email !== me && (
                      <button type="button" className="a-btn sm danger" onClick={() => role(x.email, "member")}>
                        {t("取消管理员")}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {s.staff.length === 1 && <p className="a-muted small a-pad">{t("现在只有站长能进后台（门禁名单上只有你）。")}</p>}
      </Card>
      <Card title={t("安全规则（已定）")} pad={false}>
        <table className="a-t">
          <tbody>
            {rules.map(([a, b]) => (
              <tr key={a}>
                <td>{a}</td>
                <td className="a-muted">{b}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <Card
        title={t("你在哪些设备登录了后台")}
        pad={false}
        right={
          s.sessions.length > 1 && (
            <button type="button" className="a-btn sm" onClick={() => endSession(null)}>
              {t("退出其他设备")}
            </button>
          )
        }
      >
        <table className="a-t">
          <tbody>
            {s.sessions.map((x) => (
              <tr key={x.id}>
                <td>{x.agent || t("未知设备")}</td>
                <td className="a-muted">
                  {t("登录于 {t}", { t: fmtTime(x.created) })}
                  {x.country ? ` · ${x.country}` : ""}
                </td>
                <td className="n">
                  {x.current ? (
                    <Pill tone="acc">{t("这台设备")}</Pill>
                  ) : (
                    <button type="button" className="a-btn sm" onClick={() => endSession(x.id)}>
                      {t("退出")}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
