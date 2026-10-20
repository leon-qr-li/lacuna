import { useEffect } from "react";
import { t } from "../../i18n";
import { loadProjects } from "../projects/api";
import { useShow } from "./api";
import { ShowForm } from "./ShowForm";

/** #/show, the old 节目设置: it is 项目设置 now (features/projects). */
export function ShowView() {
  useEffect(() => {
    window.location.replace("#/project");
  }, []);
  return null;
}

/** First visit to a new project (首页): its name, language and hosts before the first import. */
export function ShowSetup() {
  const show = useShow();
  if (!show?.needs_setup) return null;
  return (
    <section className="card show-setup" data-testid="show-setup">
      <h2>{show.show_name ? t("介绍一下「{name}」", { name: show.show_name }) : t("建你的第一个项目")}</h2>
      <p className="muted">{t("一档播客、一个客户、一个栏目都可以是一个项目。填名字和主持人，每位主持人一条分轨；这些以后都能在项目设置里改。")}</p>
      <ShowForm show={show} compact onSaved={() => void loadProjects(true)} />
    </section>
  );
}
