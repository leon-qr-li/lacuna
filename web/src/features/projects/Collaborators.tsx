import { useEffect, useState } from "react";
import { t, type Lang } from "../../i18n";
import { MailLang, defaultMailLang } from "../auth/MailLang";
import { confirmDialog } from "../dialog/Dialog";
import { BusyLabel } from "../loading/Loading";
import { SPACE_ROLE } from "../spaces/SpacesCard";
import { spacesApi, type ProjectPeople, type SpaceRole } from "../spaces/api";
import { loadProjects } from "./api";

const ROLES: SpaceRole[] = ["admin", "editor", "viewer"];

/** 邀请协作: invite by email into this project, and its collaborators (role, 移出) and pending invites (撤回).
 *  Only the project's managers change anything; the others see who is in it. */
export function Collaborators({ id, me, manage }: { id: string; me: string | null; manage: boolean }) {
  const [p, setP] = useState<ProjectPeople | null>(null);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<SpaceRole>("editor");
  const [mailLang, setMailLang] = useState<Lang>(defaultMailLang);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [link, setLink] = useState<string | null>(null);
  useEffect(() => {
    spacesApi.people(id).then(setP, (e) => setErr((e as Error).message));
  }, [id]);

  const act = async (what: string, fn: () => Promise<ProjectPeople>) => {
    setBusy(what);
    setErr(null);
    setNote(null);
    setLink(null);
    try {
      const r = await fn();
      setP(r);
      void loadProjects(true);
      return r;
    } catch (e) {
      setErr((e as Error).message);
      return null;
    } finally {
      setBusy(null);
    }
  };
  const invite = async () => {
    const r = await act("invite", () => spacesApi.invite(id, email.trim(), role, mailLang));
    if (!r) return;
    setEmail("");
    if (r.joined) setNote(t("{email} 已经加进来了", { email: r.joined }));
    else if (r.invited) {
      setNote(r.mailed ? t("邀请已经发到 {email}", { email: r.invited }) : t("没能发邮件，把下面的链接发给 {email}", { email: r.invited }));
      if (!r.mailed && r.link) setLink(r.link);
    }
  };
  if (!p) return err ? <p className="error small">{err}</p> : null;
  return (
    <div className="prj-collab" data-testid="collaborators">
      {manage && (
        <form
          className="prj-invite"
          onSubmit={(e) => {
            e.preventDefault();
            if (email.trim() && !busy) void invite();
          }}
        >
          <input
            className="grow"
            inputMode="email"
            placeholder={t("对方的邮箱")}
            aria-label={t("对方的邮箱")}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            data-testid="invite-email"
          />
          <select aria-label={t("角色")} value={role} onChange={(e) => setRole(e.target.value as SpaceRole)} data-testid="invite-role">
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {SPACE_ROLE[r]}
              </option>
            ))}
          </select>
          {p.can_invite_new && <MailLang value={mailLang} onChange={setMailLang} />}
          <button className="btn btn-primary" disabled={!!busy || !email.trim()} data-testid="invite-send">
            <BusyLabel busy={busy === "invite"} label={t("邀请")} />
          </button>
        </form>
      )}
      <p className="muted small prj-hint">
        {t("对方能看到这个项目的所有剧集、专辑和素材，看不到你的其他项目。管理：管协作者、彻底删除剧集；剪辑：所有剪辑工作；只听：只能试听和查看。")}
        {manage && !p.can_invite_new && ` ${t("还没有 LACUNA 账号的人，请 LACUNA 管理员邀请。")}`}
      </p>
      {note && (
        <p className="ok small" role="status">
          {note}
        </p>
      )}
      {link && <input className="prj-link" readOnly value={link} aria-label={t("邀请链接")} onFocus={(e) => e.target.select()} />}
      {err && (
        <p className="error small" role="alert">
          {err}
        </p>
      )}
      <h3 className="sub">{t("协作者")}</h3>
      <ul className="prj-people">
        {p.members.map((m) => (
          <li key={m.email} data-testid="collaborator">
            <span className="prj-avatar" aria-hidden="true">
              {m.email.slice(0, 1).toUpperCase()}
            </span>
            <span className="prj-who">
              {m.email}
              {m.email === me && <span className="muted">{t("（你）")}</span>}
            </span>
            {manage && m.email !== me ? (
              <>
                <select
                  aria-label={t("{email} 在这个项目的角色", { email: m.email })}
                  value={m.role}
                  disabled={!!busy}
                  onChange={(e) => void act("role", () => spacesApi.member(id, m.email, e.target.value as SpaceRole).then(() => spacesApi.people(id)))}
                >
                  {ROLES.map((r) => (
                    <option key={r} value={r}>
                      {SPACE_ROLE[r]}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  className="btn btn-ghost btn-small"
                  disabled={!!busy}
                  onClick={async () => {
                    const ok = await confirmDialog({
                      message: t("把 {email} 移出「{name}」？对方就看不到这个项目了，已经做的内容留着。", { email: m.email, name: p.name }),
                      confirmLabel: t("移出"),
                      danger: true,
                    });
                    if (ok) void act("rm", () => spacesApi.member(id, m.email, null).then(() => spacesApi.people(id)));
                  }}
                >
                  {t("移出")}
                </button>
              </>
            ) : (
              <span className="prj-role">{SPACE_ROLE[m.role]}</span>
            )}
          </li>
        ))}
        {p.invites.map((i) => (
          <li key={i.id} className="prj-pending" data-testid="pending-invite">
            <span className="prj-avatar" aria-hidden="true">
              {i.email.slice(0, 1).toUpperCase()}
            </span>
            <span className="prj-who">{i.email}</span>
            <span className="prj-role">{t("{role} · 待接受", { role: SPACE_ROLE[i.role] })}</span>
            {manage && (
              <button type="button" className="btn btn-ghost btn-small" disabled={!!busy} onClick={() => void act("withdraw", () => spacesApi.withdraw(id, i.id))}>
                {t("撤回")}
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
