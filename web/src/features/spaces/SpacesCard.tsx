import { useEffect, useState } from "react";
import { spacesApi, type SpaceInfo, type SpaceRole, type Spaces } from "./api";
import { authApi } from "../auth/api";
import { confirmDialog } from "../dialog/Dialog";
import { BusyLabel } from "../loading/Loading";
import { t } from "../../i18n";

export const SPACE_ROLE: Record<SpaceRole, string> = { admin: t("管理"), editor: t("剪辑"), viewer: t("只听") };
const ROLES: SpaceRole[] = ["admin", "editor", "viewer"];

/** 设置 → 工作区: where your episodes, library and learned rules live, and who shares them. */
export function SpacesCard() {
  const [sp, setSp] = useState<Spaces | null>(null);
  const [siteAdmin, setSiteAdmin] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  useEffect(() => {
    spacesApi.list().then(setSp, () => setSp(null));
    authApi.status().then((s) => setSiteAdmin(s.role === "owner" || s.role === "admin"), () => setSiteAdmin(false));
  }, []);
  if (!sp?.current) return null;
  const act = async (name: string, fn: () => Promise<Spaces>) => {
    setBusy(name);
    setErr(null);
    try {
      setSp(await fn());
    } catch (e) {
      setErr(String((e as Error).message ?? e));
    } finally {
      setBusy(null);
    }
  };
  const managed = sp.all ?? [];
  return (
    <section className="card account-card spaces-card" aria-label={t("节目")}>
      <div className="card-head">
        <h2>{t("节目")}</h2>
        <span className="badge badge-confirmed" data-testid="space-current">
          {t("现在在：{name}（{role}）", { name: sp.current.name, role: SPACE_ROLE[sp.current.role] })}
        </span>
      </div>
      <p className="muted small">
        {t("剧集、素材库和学到的规则都属于节目，只有它的成员能看到。管理：管成员、彻底删除剧集；剪辑：所有剪辑工作；只听：只能试听和查看。")}
      </p>
      {managed.map((s) => (
        <SpaceBlock key={s.id} s={s} current={s.id === sp.current!.id} busy={busy} act={act} />
      ))}
      {siteAdmin && (
        <form
          className="row gap8 account-wrap"
          onSubmit={(e) => {
            e.preventDefault();
            act("create", async () => {
              const r = await spacesApi.create(newName);
              setNewName("");
              return r;
            });
          }}
        >
          <input className="grow" placeholder={t("新节目的名字")} aria-label={t("新节目的名字")} value={newName} onChange={(e) => setNewName(e.target.value)} />
          <button className="btn btn-outline" disabled={!!busy || !newName.trim()}>
            <BusyLabel busy={busy === "create"} label={t("新建节目")} />
          </button>
        </form>
      )}
      {err && (
        <p className="error small" role="status">
          {err}
        </p>
      )}
    </section>
  );
}

function SpaceBlock({ s, current, busy, act }: {
  s: SpaceInfo;
  current: boolean;
  busy: string | null;
  act: (name: string, fn: () => Promise<Spaces>) => void;
}) {
  const [name, setName] = useState(s.name);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<SpaceRole>("editor");
  return (
    <div className="space-block" data-testid={`space-${s.id}`}>
      <div className="space-title">
        <input value={name} aria-label={t("节目名字")} onChange={(e) => setName(e.target.value)} />
        {name.trim() !== s.name && (
          <button className="btn btn-outline btn-small" disabled={!!busy} onClick={() => act("rename", () => spacesApi.rename(s.id, name))}>
            {t("改名")}
          </button>
        )}
        {current && <span className="muted small">{t("当前")}</span>}
      </div>
      <ul className="people-list">
        {s.members.map((m) => (
          <li key={m.email}>
            <div className="people-who">
              <strong>{m.email}</strong>
            </div>
            <div className="people-actions">
              <select
                aria-label={t("{email} 在这个节目的角色", { email: m.email })}
                value={m.role}
                disabled={!!busy}
                onChange={(e) => act("role", () => spacesApi.member(s.id, m.email, e.target.value as SpaceRole))}
              >
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {SPACE_ROLE[r]}
                  </option>
                ))}
              </select>
              <button
                className="btn btn-outline btn-small"
                disabled={!!busy}
                onClick={async () => {
                  if (!(await confirmDialog({ message: t("把 {email} 移出「{name}」？对方就看不到这个节目了，已经做的内容留着。", { email: m.email, name: s.name }), confirmLabel: t("移出") }))) return;
                  act("rm", () => spacesApi.member(s.id, m.email, null));
                }}
              >
                {t("移出")}
              </button>
            </div>
          </li>
        ))}
      </ul>
      <form
        className="row gap8 account-wrap"
        onSubmit={(e) => {
          e.preventDefault();
          act("add", async () => {
            const r = await spacesApi.member(s.id, email.trim(), role);
            setEmail("");
            return r;
          });
        }}
      >
        <input className="grow" inputMode="email" placeholder={t("已有账号的邮箱")} aria-label={t("加成员的邮箱")} value={email} onChange={(e) => setEmail(e.target.value)} />
        <select aria-label={t("角色")} value={role} onChange={(e) => setRole(e.target.value as SpaceRole)}>
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {SPACE_ROLE[r]}
            </option>
          ))}
        </select>
        <button className="btn btn-outline" disabled={!!busy || !email.trim()}>
          {t("加进来")}
        </button>
      </form>
    </div>
  );
}
