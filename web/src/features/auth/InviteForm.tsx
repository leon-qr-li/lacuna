import { useEffect, useState } from "react";
import { PLAN_IDS, type PlanId, type Role } from "./api";
import { MailLang, defaultMailLang } from "./MailLang";
import { plansApi, type PlanLimits } from "../plans/api";
import { SPACE_ROLE } from "../spaces/SpacesCard";
import type { SpaceInfo, SpaceRole } from "../spaces/api";
import { BusyLabel } from "../loading/Loading";
import { t, type Lang } from "../../i18n";
import "./invite_form.css";

export interface InviteFields {
  email: string;
  role: Role;
  space: string;
  spaceRole: SpaceRole | null;
  lang: Lang;
  plan: PlanId;
}

/** "基础版 · 每月 4 小时 · 1 个节目" from the plan table; the name alone until it has loaded */
function planLabel(name: string, p: PlanLimits | undefined): string {
  if (!p) return name;
  const hours = p.hours === null ? t("时长不限") : p.hours_once ? t("一次性 {n} 小时", { n: p.hours }) : t("每月 {n} 小时", { n: p.hours });
  const shows = p.shows === null ? t("节目不限") : t("{n} 个节目", { n: p.shows });
  return `${name} · ${hours} · ${shows}`;
}

/** 设置 → 成员与邀请: the invite form in three sections, who / which show / which plan (design B 「分区表单」,
 *  Leon 2026-10-21). Field names and test ids are the same as the one-line form it replaces. */
export function InviteForm({ grantable, roleNames, planNames, spaces, busy, onSend }: {
  grantable: Role[];
  roleNames: Record<Role, string>;
  planNames: Record<PlanId, string>;
  spaces: SpaceInfo[];
  busy: string | null;
  onSend: (f: InviteFields, done: () => void) => void;
}) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("member");
  const [space, setSpace] = useState("new");
  const [spaceRole, setSpaceRole] = useState<SpaceRole>("editor");
  const [lang, setLang] = useState<Lang>(defaultMailLang);
  const [plan, setPlan] = useState<PlanId>("basic");
  const [table, setTable] = useState<PlanLimits[]>([]);
  useEffect(() => {
    plansApi.mine().then((p) => setTable(p.plans), () => setTable([]));
  }, []);
  return (
    <form
      className="invite-form"
      data-testid="invite-form"
      onSubmit={(e) => {
        e.preventDefault();
        onSend({ email, role, space, spaceRole: space === "new" ? null : spaceRole, lang, plan }, () => setEmail(""));
      }}
    >
      <h3>{t("邀请新成员")}</h3>
      <div className="invite-sec">
        <div className="invite-sec-head">
          <strong>{t("对方")}</strong>
          <span>{t("邀请邮件发到这个地址")}</span>
        </div>
        <div className="invite-fields">
          <input type="text" inputMode="email" autoComplete="off" required placeholder="name@example.com" aria-label={t("对方的邮箱")} value={email} onChange={(e) => setEmail(e.target.value)} />
          <div className="invite-two">
            <label className="invite-label">
              {t("站点角色")}
              <select aria-label={t("角色")} value={role} onChange={(e) => setRole(e.target.value as Role)}>
                {grantable.map((r) => (
                  <option key={r} value={r}>
                    {roleNames[r]}
                  </option>
                ))}
              </select>
            </label>
            <label className="invite-label">
              {t("邮件语言")}
              <MailLang value={lang} onChange={setLang} />
            </label>
          </div>
        </div>
      </div>
      <div className="invite-sec">
        <div className="invite-sec-head">
          <strong>{t("节目")}</strong>
          <span>{t("加入现有节目，或给对方新建一个")}</span>
        </div>
        <div className="invite-two">
          <label className="invite-label">
            {t("节目")}
            <select aria-label={t("加入哪个节目")} value={space} onChange={(e) => setSpace(e.target.value)} data-testid="invite-space">
              <option value="new">{t("给对方新建一个节目")}</option>
              {spaces.map((s) => (
                <option key={s.id} value={s.id}>
                  {t("加入「{name}」", { name: s.name })}
                </option>
              ))}
            </select>
          </label>
          <label className="invite-label">
            {t("节目里的角色")}
            {space === "new" ? (
              <select disabled aria-label={t("在节目里的角色")} value="admin">
                <option value="admin">{t("新建时为管理员")}</option>
              </select>
            ) : (
              <select aria-label={t("在节目里的角色")} value={spaceRole} onChange={(e) => setSpaceRole(e.target.value as SpaceRole)}>
                {(["admin", "editor", "viewer"] as SpaceRole[]).map((r) => (
                  <option key={r} value={r}>
                    {SPACE_ROLE[r]}
                  </option>
                ))}
              </select>
            )}
          </label>
        </div>
      </div>
      <div className="invite-sec">
        <div className="invite-sec-head">
          <strong>{t("套餐")}</strong>
          <span>{t("决定可用时长和节目数")}</span>
        </div>
        <select aria-label={t("套餐")} value={plan} onChange={(e) => setPlan(e.target.value as PlanId)} data-testid="invite-plan">
          {PLAN_IDS.map((p) => (
            <option key={p} value={p}>
              {planLabel(planNames[p], table.find((x) => x.id === p))}
            </option>
          ))}
        </select>
      </div>
      <div className="invite-foot">
        <span className="muted small">{t("对方会收到一封邀请邮件，也可以复制链接直接发给对方。")}</span>
        <button className="btn btn-primary" disabled={!!busy || !email}>
          <BusyLabel busy={busy === "invite"} label={t("发送邀请")} busyLabel={t("发送中…")} />
        </button>
      </div>
    </form>
  );
}
