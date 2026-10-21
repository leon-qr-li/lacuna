import { useCallback, useEffect, useState, type ReactNode } from "react";
import { AUTH_EVENT, authApi, type AuthStatus, type Device, type People, type Role } from "./api";
import { CodeInput, RecoveryCodes, SecondFactor, TwoStepQR } from "./TwoStep";
import { confirmDialog } from "../dialog/Dialog";
import { spacesApi, type SpaceInfo, type SpaceRole } from "../spaces/api";
import { SPACE_ROLE } from "../spaces/SpacesCard";
import { BusyLabel } from "../loading/Loading";
import { t, type Lang } from "../../i18n";
import { MailLang, defaultMailLang } from "./MailLang";
import "./auth.css";

const KEY_SOURCE: Record<string, string> = {
  env: t("环境变量"),
  "registry-user": t("Windows 用户环境变量"),
  keychain: t("macOS 钥匙串"),
  file: t("本机文件"),
  test: t("测试"),
};

export const ROLE: Record<Role, string> = { owner: t("所有者"), admin: t("管理员"), member: t("成员") };
const RANK: Record<Role, number> = { member: 1, admin: 2, owner: 3 };

type Msg = { ok: boolean; text: string } | null;

/** One busy action at a time per card, with its result or error under the card. */
function useAct() {
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<Msg>(null);
  const act = async (name: string, fn: () => Promise<string | void>) => {
    setBusy(name);
    setMsg(null);
    try {
      const text = await fn();
      if (text) setMsg({ ok: true, text });
    } catch (e) {
      setMsg({ ok: false, text: String((e as Error).message ?? e) });
    } finally {
      setBusy(null);
    }
  };
  return { busy, msg, act, setMsg };
}

function Note({ msg }: { msg: Msg }) {
  return msg ? (
    <p className={msg.ok ? "account-ok small" : "error small"} role="status">
      {msg.text}
    </p>
  ) : null;
}

const when = (s: number | null) => (s ? new Date(s * 1000).toLocaleString() : "—");

/** "Chrome · Windows" from a user agent. */
function device(agent: string): string {
  const browser = /Edg\//.test(agent) ? "Edge" : /Firefox\//.test(agent) ? "Firefox" : /Chrome\//.test(agent) ? "Chrome" : /Safari\//.test(agent) ? "Safari" : "";
  const os = /iPhone|iPad/.test(agent) ? "iOS" : /Android/.test(agent) ? "Android" : /Windows/.test(agent) ? "Windows" : /Mac OS X/.test(agent) ? "macOS" : /Linux/.test(agent) ? "Linux" : "";
  return [browser, os].filter(Boolean).join(" · ") || agent.slice(0, 60) || t("未知设备");
}

/** The signed-in account (null while loading or without sign-in); `setSt` after a change. */
export function useAuthStatus() {
  const [st, setSt] = useState<AuthStatus | null>(null);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    authApi.status().then(
      (s) => {
        setSt(s);
        setLoaded(true);
      },
      () => {
        setSt(null);
        setLoaded(true);
      },
    );
  }, []);
  return { st, setSt, loaded };
}

/** 设置: my account and security (everyone), email (owner), members and invites (owner, admins). */
export function AccountCard() {
  const [st, setSt] = useState<AuthStatus | null>(null);
  const load = useCallback(() => {
    authApi.status().then(setSt, () => setSt(null));
  }, []);
  useEffect(load, [load]);
  if (!st || !st.email || !st.role) return null;
  return (
    <>
      <SecurityCard st={st} setSt={setSt} />
      {st.role !== "member" && <MembersCard me={st.email} role={st.role} />}
      {st.role === "owner" && st.mail && <MailCard st={st} setSt={setSt} />}
    </>
  );
}

export function SecurityCard({ st, setSt }: { st: AuthStatus; setSt: (s: AuthStatus) => void }) {
  const { busy, msg, act } = useAct();
  return (
    <section className="card account-card" aria-label={t("账号与安全")}>
      <div className="card-head">
        <h2>{t("账号与安全")}</h2>
        <button
          className="btn btn-outline btn-small"
          disabled={!!busy}
          onClick={() =>
            act("logout", async () => {
              await authApi.logout();
              window.dispatchEvent(new Event(AUTH_EVENT));
            })
          }
        >
          {t("退出登录")}
        </button>
      </div>
      <p className="muted small" data-testid="account-email">
        {t("已登录：{email}", { email: st.email })} · <span data-testid="account-role">{ROLE[st.role!]}</span>
      </p>
      <TwoStepRow st={st} setSt={setSt} />
      <PasswordRow />
      <Devices />
      <Note msg={msg} />
    </section>
  );
}

function Row({ title, help, children }: { title: string; help: string; children?: ReactNode }) {
  return (
    <div className="set-row">
      <div>
        <strong>{title}</strong>
        <p className="muted small">{help}</p>
      </div>
      {children}
    </div>
  );
}

/** Two-step sign-in: turn on (scan + confirm + recovery codes), new recovery codes, turn off (desktop only). */
function TwoStepRow({ st, setSt }: { st: AuthStatus; setSt: (s: AuthStatus) => void }) {
  const [mode, setMode] = useState<null | "setup" | "recovery" | "off">(null);
  const [setup, setSetup] = useState<{ secret: string; uri: string } | null>(null);
  const [codes, setCodes] = useState<string[] | null>(null);
  const [code, setCode] = useState("");
  const { busy, msg, act, setMsg } = useAct();
  const close = () => {
    setMode(null);
    setSetup(null);
    setCode("");
  };
  return (
    <>
      <Row
        title={t("两步验证")}
        help={
          st.require_2fa
            ? t("登录时除了密码，还要手机验证器 App 上的 6 位数字。云端版每个账号都必须开。")
            : t("登录时除了密码，还要手机验证器 App 上的 6 位数字。这台电脑上可选，上云后必须开。")
        }
      >
        <span className={st.twofa ? "badge badge-confirmed" : "badge badge-unknown"} data-testid="twostep-state">
          {st.twofa ? t("已开启") : t("没开启")}
        </span>
      </Row>
      {codes ? (
        <RecoveryCodes
          codes={codes}
          email={st.email!}
          doneLabel={t("完成")}
          onDone={() => {
            setCodes(null);
            setMsg({ ok: true, text: t("两步验证设置好了。") });
          }}
        />
      ) : mode === "setup" && setup ? (
        <div>
          <TwoStepQR uri={setup.uri} secret={setup.secret} />
          <CodeInput value={code} onChange={setCode} label={t("两步验证码")} />
          <div className="row gap8 account-wrap">
            <button
              className="btn btn-primary"
              disabled={!!busy || code.length < 6}
              onClick={() =>
                act("confirm", async () => {
                  const r = await authApi.confirm2fa(code);
                  setSt(r);
                  setCodes(r.recovery);
                  close();
                })
              }
            >
              <BusyLabel busy={busy === "confirm"} label={t("确认开启")} />
            </button>
            <button className="btn btn-outline" onClick={close}>
              {t("取消")}
            </button>
          </div>
        </div>
      ) : mode ? (
        <div>
          <SecondFactor value={code} onChange={setCode} />
          <div className="row gap8 account-wrap">
            <button
              className={mode === "off" ? "btn btn-outline account-danger" : "btn btn-primary"}
              disabled={!!busy || code.length < 6}
              onClick={() =>
                act("code", async () => {
                  if (mode === "off") setSt(await authApi.off2fa(code));
                  else setCodes((await authApi.newRecovery(code)).recovery);
                  close();
                })
              }
            >
              <BusyLabel busy={busy === "code"} label={mode === "off" ? t("关闭两步验证") : t("生成新的恢复码")} />
            </button>
            <button className="btn btn-outline" onClick={close}>
              {t("取消")}
            </button>
          </div>
        </div>
      ) : (
        <div className="row gap8 account-wrap">
          {!st.twofa ? (
            <button
              className="btn btn-outline"
              disabled={!!busy}
              onClick={() =>
                act("setup", async () => {
                  setSetup(await authApi.setup2fa());
                  setMode("setup");
                })
              }
            >
              {t("开启两步验证")}
            </button>
          ) : (
            <>
              <button className="btn btn-outline btn-small" onClick={() => setMode("recovery")}>
                {t("换一组恢复码")}
              </button>
              {!st.require_2fa && (
                <button className="btn btn-outline btn-small" onClick={() => setMode("off")}>
                  {t("关闭")}
                </button>
              )}
            </>
          )}
        </div>
      )}
      <Note msg={msg} />
    </>
  );
}

function PasswordRow() {
  const [open, setOpen] = useState(false);
  const [old, setOld] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const { busy, msg, act, setMsg } = useAct();
  return (
    <>
      <Row title={t("密码")} help={t("改密码后，其他设备要重新登录。")}>
        {!open && (
          <button className="btn btn-outline btn-small" onClick={() => setOpen(true)}>
            {t("修改密码")}
          </button>
        )}
      </Row>
      {open && (
        <div className="account-stack">
          <input type="password" autoComplete="current-password" placeholder={t("现在的密码")} aria-label={t("现在的密码")} value={old} onChange={(e) => setOld(e.target.value)} />
          <input type="password" autoComplete="new-password" placeholder={t("新密码（至少 10 位）")} aria-label={t("新密码")} value={pw} onChange={(e) => setPw(e.target.value)} />
          <input type="password" autoComplete="new-password" placeholder={t("再输一次新密码")} aria-label={t("确认新密码")} value={pw2} onChange={(e) => setPw2(e.target.value)} />
          <div className="row gap8 account-wrap">
            <button
              className="btn btn-primary"
              disabled={!!busy || !old || !pw}
              onClick={() => {
                if (pw !== pw2) return setMsg({ ok: false, text: t("两次输入的密码不一样") });
                act("pw", async () => {
                  await authApi.password(old, pw);
                  setOpen(false);
                  setOld("");
                  setPw("");
                  setPw2("");
                  return t("密码改好了。");
                });
              }}
            >
              <BusyLabel busy={busy === "pw"} label={t("保存新密码")} />
            </button>
            <button className="btn btn-outline" onClick={() => setOpen(false)}>
              {t("取消")}
            </button>
          </div>
        </div>
      )}
      <Note msg={msg} />
    </>
  );
}

function Devices() {
  const [rows, setRows] = useState<Device[]>([]);
  const { busy, msg, act } = useAct();
  useEffect(() => {
    authApi.devices().then((r) => setRows(r.sessions), () => setRows([]));
  }, []);
  const end = (id: string | null) =>
    act(id ?? "all", async () => {
      const r = await authApi.endDevices(id);
      setRows(r.sessions);
      return t("已退出 {n} 台设备。", { n: r.ended });
    });
  return (
    <>
      <h3>{t("登录中的设备")}</h3>
      <ul className="people-list" data-testid="devices">
        {rows.map((d) => (
          <li key={d.id}>
            <div className="people-who">
              <strong>{device(d.agent)}</strong>
              <span className="muted small">{t("登录于 {a} · 最近使用 {b}", { a: when(d.created), b: when(d.seen) })}</span>
            </div>
            {d.current ? (
              <span className="badge badge-confirmed">{t("这台设备")}</span>
            ) : (
              <button className="btn btn-outline btn-small" disabled={!!busy} onClick={() => end(d.id)}>
                {t("退出")}
              </button>
            )}
          </li>
        ))}
      </ul>
      {rows.length > 1 && (
        <button className="btn btn-outline btn-small" disabled={!!busy} onClick={() => end(null)}>
          {t("退出其他所有设备")}
        </button>
      )}
      <Note msg={msg} />
    </>
  );
}

/** Owner and admins: invite by email (one-time link, 7 days), pending invites, members. */
export function MembersCard({ me, role }: { me: string; role: Role }) {
  const [people, setPeople] = useState<People | null>(null);
  const [email, setEmail] = useState("");
  const [newRole, setNewRole] = useState<Role>("member");
  const [link, setLink] = useState<{ link: string; email: string; mailed: boolean; why: string | null } | null>(null);
  const [copied, setCopied] = useState(false);
  const [spaces, setSpaces] = useState<SpaceInfo[]>([]);
  const [space, setSpace] = useState("new");
  const [spaceRole, setSpaceRole] = useState<SpaceRole>("editor");
  const [mailLang, setMailLang] = useState<Lang>(defaultMailLang);
  const { busy, msg, act } = useAct();
  useEffect(() => {
    authApi.people().then(setPeople, () => setPeople(null));
    spacesApi.list().then((s) => setSpaces(s?.all ?? []), () => setSpaces([]));
  }, []);
  if (!people) return null;
  const canManage = (r: Role) => RANK[role] > RANK[r];
  const grantable: Role[] = role === "owner" ? ["member", "admin"] : ["member"];
  return (
    <section className="card account-card" aria-label={t("成员与邀请")}>
      <div className="card-head">
        <h2>{t("成员与邀请")}</h2>
      </div>
      <p className="muted small">
        {t("LACUNA 只对受邀请的人开放。邀请链接绑定邮箱，7 天内有效，只能用一次。管理员能邀请和管理成员；只有所有者能设管理员、改 AI 密钥和邮件设置。")}
      </p>
      <form
        className="row gap8 account-wrap"
        onSubmit={(e) => {
          e.preventDefault();
          act("invite", async () => {
            const r = await authApi.sendInvite(email, newRole, space, space === "new" ? null : spaceRole, mailLang);
            setPeople(r);
            setLink({ link: r.link, email: r.email, mailed: r.mailed, why: r.mail_error });
            setCopied(false);
            setEmail("");
          });
        }}
      >
        <input className="grow" type="text" inputMode="email" autoComplete="off" required placeholder={t("对方的邮箱")} aria-label={t("对方的邮箱")} value={email} onChange={(e) => setEmail(e.target.value)} />
        <select aria-label={t("角色")} value={newRole} onChange={(e) => setNewRole(e.target.value as Role)}>
          {grantable.map((r) => (
            <option key={r} value={r}>
              {ROLE[r]}
            </option>
          ))}
        </select>
        {spaces.length > 0 && (
          <select aria-label={t("加入哪个项目")} value={space} onChange={(e) => setSpace(e.target.value)} data-testid="invite-space">
            <option value="new">{t("给对方新建一个项目")}</option>
            {spaces.map((s) => (
              <option key={s.id} value={s.id}>
                {t("加入「{name}」", { name: s.name })}
              </option>
            ))}
          </select>
        )}
        {space !== "new" && (
          <select aria-label={t("在项目里的角色")} value={spaceRole} onChange={(e) => setSpaceRole(e.target.value as SpaceRole)}>
            {(["admin", "editor", "viewer"] as SpaceRole[]).map((r) => (
              <option key={r} value={r}>
                {SPACE_ROLE[r]}
              </option>
            ))}
          </select>
        )}
        <MailLang value={mailLang} onChange={setMailLang} />
        <button className="btn btn-primary" disabled={!!busy || !email}>
          <BusyLabel busy={busy === "invite"} label={t("发送邀请")} busyLabel={t("发送中…")} />
        </button>
      </form>
      {link && (
        <div data-testid="invite-result">
          <p className={link.mailed ? "account-ok small" : "muted small"}>
            {link.mailed
              ? t("邀请邮件已发到 {email}。也可以把下面的链接直接发给对方。", { email: link.email })
              : t("邮件没发出去（{why}）。把下面的链接复制给 {email} 就行。", { why: link.why ?? "", email: link.email })}
          </p>
          <div className="people-link">
            <code data-testid="invite-link">{link.link}</code>
            <button
              type="button"
              className="btn btn-outline btn-small"
              onClick={() => navigator.clipboard?.writeText(link.link).then(() => setCopied(true), () => setCopied(false))}
            >
              {copied ? t("已复制") : t("复制链接")}
            </button>
          </div>
        </div>
      )}

      {people.invites.length > 0 && (
        <>
          <h3>{t("等待接受的邀请")}</h3>
          <ul className="people-list" data-testid="invites">
            {people.invites.map((i) => (
              <li key={i.id}>
                <div className="people-who">
                  <strong>{i.email}</strong>
                  <span className="muted small">{t("{role} · {by} 邀请 · {exp} 过期", { role: ROLE[i.role], by: i.by, exp: when(i.exp) })}</span>
                </div>
                <button className="btn btn-outline btn-small" disabled={!!busy} onClick={() => act("revoke", async () => setPeople(await authApi.revokeInvite(i.id)))}>
                  {t("撤回")}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}

      <h3>{t("成员")}</h3>
      <ul className="people-list" data-testid="members">
        {people.users.map((u) => {
          const can = u.email !== me && canManage(u.role);
          return (
            <li key={u.email} className={u.disabled ? "is-off" : ""}>
              <div className="people-who">
                <strong>{u.email}</strong>
                <span className="muted small">
                  {[ROLE[u.role], u.twofa ? t("已开两步验证") : t("没开两步验证"), u.disabled ? t("已停用") : t("最近使用 {b}", { b: when(u.seen) })].join(" · ")}
                </span>
              </div>
              {can && (
                <div className="people-actions">
                  {role === "owner" && (
                    <select
                      aria-label={t("{email} 的角色", { email: u.email })}
                      value={u.role}
                      disabled={!!busy}
                      onChange={(e) => act("role", async () => setPeople(await authApi.updateMember(u.email, { role: e.target.value as Role })))}
                    >
                      {grantable.map((r) => (
                        <option key={r} value={r}>
                          {ROLE[r]}
                        </option>
                      ))}
                    </select>
                  )}
                  {u.twofa && (
                    <button
                      className="btn btn-outline btn-small"
                      disabled={!!busy}
                      onClick={async () => {
                        if (!(await confirmDialog({ message: t("重置 {email} 的两步验证？对方下次登录时要重新扫码设置（适合手机丢了的情况）。", { email: u.email }), confirmLabel: t("重置") }))) return;
                        act("reset", async () => setPeople(await authApi.updateMember(u.email, { reset_2fa: true })));
                      }}
                    >
                      {t("重置两步验证")}
                    </button>
                  )}
                  <button
                    className="btn btn-outline btn-small"
                    disabled={!!busy}
                    onClick={() => act("off", async () => setPeople(await authApi.updateMember(u.email, { disabled: !u.disabled })))}
                  >
                    {u.disabled ? t("恢复") : t("停用")}
                  </button>
                  <button
                    className="btn btn-outline btn-small"
                    disabled={!!busy}
                    onClick={async () => {
                      if (!(await confirmDialog({ message: t("删除 {email} 的账号？对方马上退出登录，也不能再登录。对方做过的剧集和素材留着。", { email: u.email }), danger: true, confirmLabel: t("删除账号") }))) return;
                      act("rm", async () => setPeople(await authApi.removeMember(u.email)));
                    }}
                  >
                    {t("删除")}
                  </button>
                </div>
              )}
            </li>
          );
        })}
      </ul>
      <Note msg={msg} />
    </section>
  );
}

/** Owner: the Resend key and sender for invite and password-reset emails. */
export function MailCard({ st, setSt }: { st: AuthStatus; setSt: (s: AuthStatus) => void }) {
  const mail = st.mail!;
  const [key, setKey] = useState("");
  const [sender, setSender] = useState(mail.sender);
  const { busy, msg, act } = useAct();
  return (
    <section className="card account-card" aria-label={t("邮件")}>
      <div className="card-head">
        <h2>{t("邮件")}</h2>
      </div>
      <Row title="Resend API key" help={t("邀请邮件和「忘记密码」的验证码用 Resend 发。只保存在这台机器上，不会显示出来。")}>
        <span className={mail.configured ? "badge badge-confirmed" : "badge badge-unknown"} data-testid="resend-state">
          {mail.configured ? t("已接上（{p0}）", { p0: KEY_SOURCE[mail.source ?? ""] ?? mail.source }) : t("还没接上")}
        </span>
      </Row>
      {st.cloud ? (
        <p className="muted small">{t("云端版的 key 在服务器的环境变量里设置，不能在网页上改。")}</p>
      ) : (
      <div className="row gap8 account-wrap">
        <input className="grow" type="password" autoComplete="off" placeholder="re_…" aria-label="Resend API key" value={key} onChange={(e) => setKey(e.target.value)} />
        <button
          className="btn btn-outline"
          disabled={!!busy || key.trim().length < 20}
          onClick={() =>
            act("key", async () => {
              setSt(await authApi.saveResendKey(key));
              setKey("");
              return t("已保存。");
            })
          }
        >
          <BusyLabel busy={busy === "key"} label={mail.configured ? t("换一个") : t("保存")} />
        </button>
      </div>
      )}
      <Row title={t("发件地址")} help={t("没验证域名时用 onboarding@resend.dev，只能发到你注册 Resend 的邮箱。验证了域名就改成那个域名下的地址。")} />
      <div className="row gap8 account-wrap">
        <input className="grow" value={sender} aria-label={t("发件地址")} onChange={(e) => setSender(e.target.value)} />
        <button className="btn btn-outline" disabled={!!busy || sender.trim() === mail.sender} onClick={() => act("sender", async () => setSt(await authApi.config({ sender })))}>
          {t("保存")}
        </button>
        <button
          className="btn btn-outline"
          disabled={!!busy || !mail.configured}
          onClick={() => act("test", async () => t("测试邮件已发到 {to}，去收件箱看看。", { to: (await authApi.testMail()).to }))}
        >
          <BusyLabel busy={busy === "test"} label={t("发测试邮件")} busyLabel={t("发送中…")} />
        </button>
      </div>
      <Note msg={msg} />
    </section>
  );
}
