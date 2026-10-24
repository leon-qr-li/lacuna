import { useEffect, useState } from "react";
import { feedbackApi } from "../feedback/api";
import { ShowQuestions, type ShowAnswers } from "../feedback/parts";
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
  const [about, setAbout] = useState<ShowAnswers>({});
  if (!show?.needs_setup) return null;
  return (
    <section className="card show-setup" data-testid="show-setup">
      <h2>{show.show_name ? t("介绍一下「{name}」", { name: show.show_name }) : t("建你的第一个节目")}</h2>
      <p className="muted">{t("一档播客、一个客户、一个栏目都可以是一个节目。填名字和主持人；这些以后都能在节目设置里改。")}</p>
      <ShowForm
        show={show}
        compact
        extra={<ShowQuestions value={about} onChange={setAbout} />}
        onSaved={() => {
          // 让我们更了解你的节目 (features/feedback): only if answered; never holds up the setup
          if (about.region || about.editing) void feedbackApi.profile(about).catch(() => undefined);
          void loadProjects(true);
        }}
      />
    </section>
  );
}
