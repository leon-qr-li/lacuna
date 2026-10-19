import { t } from "../../i18n";
import { PageLoading } from "../loading/Loading";
import { useShow } from "./api";
import { ShowForm } from "./ShowForm";

/** 节目 (#/show): the workspace's show name, hosts and how LACUNA edits and presents it. */
export function ShowView() {
  const show = useShow();
  if (!show) return <PageLoading label={t("正在打开节目设置…")} shape="list" />;
  return (
    <main className="show-page">
      <div className="home-hero">
        <h1>{t("节目设置")}</h1>
        <p className="muted">{t("这个工作区做的节目。导入、AI 剪辑、show notes 和海报都按这里来。")}</p>
      </div>
      <section className="card">
        <ShowForm show={show} />
      </section>
    </main>
  );
}

/** First visit to a new workspace (首页): the show's name and hosts before the first import. */
export function ShowSetup() {
  const show = useShow();
  if (!show?.needs_setup) return null;
  return (
    <section className="card show-setup" data-testid="show-setup">
      <h2>{t("先介绍一下你的节目")}</h2>
      <p className="muted">{t("填节目名和主持人，每位主持人一条分轨。以后可以在「节目」里改，也能设剪辑风格。")}</p>
      <ShowForm show={show} compact />
    </section>
  );
}
