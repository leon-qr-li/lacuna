import { useState } from "react";
import { t } from "../../i18n";
import { AlbumCover } from "../albums/Cover";
import { PageLoading } from "../loading/Loading";
import { SPACE_ROLE } from "../spaces/SpacesCard";
import type { MySpace } from "../spaces/api";
import { NewProjectDialog } from "./NewProject";
import { openProject, useProjects } from "./api";

const day = (s?: number) => {
  if (!s) return "";
  const d = new Date(s * 1000);
  const today = new Date();
  if (d.toDateString() === today.toDateString()) return t("今天");
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
};

/** #/projects (所有项目): where someone with two or more projects lands after signing in. */
export function ProjectsPage() {
  const sp = useProjects();
  const [making, setMaking] = useState(false);
  if (sp === undefined) return <PageLoading label={t("正在打开项目…")} shape="list" />;
  const mine = sp?.mine ?? [];
  const card = (p: MySpace) => (
    <li key={p.id}>
      <button type="button" className="prj-card" onClick={() => void openProject(p.id)} data-testid="project-card">
        <AlbumCover a={{ id: p.id, name: p.name, cover_url: null }} size={64} />
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
    </li>
  );
  return (
    <main className="home prj-page">
      <div className="home-hero">
        <h1>{t("我的项目")}</h1>
        <p className="muted">{t("每个项目有自己的剧集、专辑和素材。别人邀请你协作的项目也在这里。")}</p>
      </div>
      <ul className="prj-grid" data-testid="project-list">
        {mine.map(card)}
        <li>
          <button type="button" className="prj-card prj-card-new" onClick={() => setMaking(true)} data-testid="project-new-card">
            {t("＋ 新项目")}
          </button>
        </li>
      </ul>
      {making && <NewProjectDialog onClose={() => setMaking(false)} />}
    </main>
  );
}
