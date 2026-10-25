import type { Feature } from "../registry";
import { t } from "../../i18n";
import { ProjectSettings, InvitePage } from "./ProjectSettings";
import { ProjectsPage } from "./ProjectsPage";
import { useProjects } from "./api";
import "./projects.css";

/** 邀请协作 in the top bar, for the project's managers: opens 节目设置 → 协作者, the one place members are
 *  managed (batch 7, T10). */
function InviteLink() {
  const sp = useProjects();
  if (sp?.current?.role !== "admin" || sp.current.archived) return null;
  return (
    <a className="btn btn-outline row" href="#/project/people" data-testid="invite-link">
      {t("邀请协作")}
    </a>
  );
}

// the project menu itself sits after LACUNA at the top left (ProjectCrumb, in each top bar)
export const feature: Feature = {
  pages: [
    { path: "projects", title: t("我的节目"), render: () => <ProjectsPage /> },
    { path: "project", title: t("节目设置"), render: () => <ProjectSettings /> },
    { path: "invite", title: t("邀请协作"), render: () => <InvitePage /> },
  ],
  nav: [{ order: 26, path: "invite", render: () => <InviteLink />, on: ["home", "page"] }],
};
