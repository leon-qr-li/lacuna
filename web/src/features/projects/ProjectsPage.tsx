import { useState } from "react";
import { t } from "../../i18n";
import { noticeDialog } from "../dialog/Dialog";
import { PageLoading } from "../loading/Loading";
import { SPACE_ROLE } from "../spaces/SpacesCard";
import { spacesApi, type MySpace } from "../spaces/api";
import { ProjectAvatar } from "./Avatar";
import { DeleteProjectDialog } from "./DeleteProject";
import { NewProjectDialog } from "./NewProject";
import { openProject, setProjects, useProjects } from "./api";

const day = (s?: number) => {
  if (!s) return "";
  const d = new Date(s * 1000);
  const today = new Date();
  if (d.toDateString() === today.toDateString()) return t("今天");
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
};

/** #/projects (所有项目): where someone with two or more projects lands after signing in. Archived
 *  projects sit apart under 已归档, where they can be restored or (by their creator) deleted for good. */
export function ProjectsPage() {
  const sp = useProjects();
  const [making, setMaking] = useState(false);
  const [deleting, setDeleting] = useState<MySpace | null>(null);
  const [err, setErr] = useState<string | null>(null);
  if (sp === undefined) return <PageLoading label={t("正在打开项目…")} shape="list" />;
  const mine = sp?.mine ?? [];
  const live = mine.filter((p) => !p.archived);
  const archived = mine.filter((p) => p.archived);
  const restore = async (p: MySpace) => {
    setErr(null);
    try {
      setProjects(await spacesApi.archive(p.id, false));
    } catch (e) {
      setErr((e as Error).message);
    }
  };
  const tryDelete = async (p: MySpace) => {
    if (mine.length < 2) {
      await noticeDialog(t("这是你唯一的项目。先新建一个项目，再删除这个。"));
      return;
    }
    setDeleting(p);
  };
  const card = (p: MySpace) => (
    <li key={p.id} className={p.archived ? "prj-archived" : undefined}>
      <button type="button" className="prj-card" onClick={() => void openProject(p.id)} data-testid="project-card">
        <ProjectAvatar p={p} size={64} />
        <span className="prj-card-body">
          <strong>{p.name}</strong>
          <span className="muted small">
            {p.albums ? t("{n} 集 · {m} 个专辑", { n: p.episodes ?? 0, m: p.albums }) : t("{n} 集", { n: p.episodes ?? 0 })}
          </span>
          <span className="muted small">
            {t("最近 {day}", { day: day(p.updated) })}
            {(p.people ?? 1) > 1 && ` · ${t("{n} 位协作者", { n: p.people! })}`}
          </span>
          {p.by && <span className="prj-by small">{t("{who} 邀请你 · {role}", { who: p.by, role: SPACE_ROLE[p.role] })}</span>}
          {p.id === sp?.current?.id && <span className="prj-here small">{t("现在在这个项目")}</span>}
        </span>
      </button>
      {p.archived && (p.role === "admin" || p.can_delete) && (
        <div className="prj-card-actions">
          {p.role === "admin" && (
            <button type="button" className="btn btn-outline btn-small" onClick={() => void restore(p)} data-testid="project-restore">
              {t("恢复")}
            </button>
          )}
          {p.can_delete && (
            <button type="button" className="btn btn-danger-outline btn-small" onClick={() => void tryDelete(p)} data-testid="project-delete">
              {t("永久删除")}
            </button>
          )}
        </div>
      )}
    </li>
  );
  return (
    <main className="home prj-page">
      <div className="home-hero">
        <h1>{t("我的项目")}</h1>
        <p className="muted">{t("每个项目有自己的剧集、专辑和素材。别人邀请你协作的项目也在这里。")}</p>
      </div>
      <ul className="prj-grid" data-testid="project-list">
        {live.map(card)}
        <li>
          <button type="button" className="prj-card prj-card-new" onClick={() => setMaking(true)} data-testid="project-new-card">
            {t("＋ 新项目")}
          </button>
        </li>
      </ul>
      {err && <p className="error small">{err}</p>}
      {!!archived.length && (
        <section className="prj-archive" data-testid="project-archive">
          <h2>{t("已归档")}</h2>
          <p className="muted small">{t("归档的项目只能查看，所有协作者都不能修改。恢复后一切照旧。")}</p>
          <ul className="prj-grid">{archived.map(card)}</ul>
        </section>
      )}
      {making && <NewProjectDialog onClose={() => setMaking(false)} />}
      {deleting && <DeleteProjectDialog p={deleting} here={deleting.id === sp?.current?.id} onClose={() => setDeleting(null)} />}
    </main>
  );
}
