import type { Feature } from "../registry";
import { navCurrent } from "../registry";
import { t } from "../../i18n";
import { ProjectSettings, InvitePage } from "./ProjectSettings";
import { ProjectsPage } from "./ProjectsPage";
import { useProjects } from "./api";
import "./projects.css";

/** 邀请协作 in the top bar, for the project's managers. */
function InviteLink() {
  const sp = useProjects();
  if (sp?.current?.role !== "admin") return null;
  return (
    <a className="btn btn-outline row" href="#/invite" aria-current={navCurrent("invite")} data-testid="invite-link">
      {t("邀请协作")}
    </a>
  );
}

// the project menu itself sits after LACUNA at the top left (ProjectCrumb, in each top bar)
export const feature: Feature = {
  pages: [
    { path: "projects", title: t("所有项目"), render: () => <ProjectsPage /> },
    { path: "project", title: t("项目设置"), render: () => <ProjectSettings /> },
    { path: "invite", title: t("邀请协作"), render: () => <InvitePage /> },
  ],
  nav: [{ order: 26, path: "invite", render: () => <InviteLink />, on: ["home", "page"] }],
};
