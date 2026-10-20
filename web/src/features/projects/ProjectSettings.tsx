import { useEffect, useState } from "react";
import { t } from "../../i18n";
import { albumsApi, type AlbumsView } from "../albums/api";
import { authApi } from "../auth/api";
import { libraryApi, type Asset } from "../library/api";
import { PageLoading } from "../loading/Loading";
import { ShowForm, type ShowPart } from "../show/ShowForm";
import { useShow } from "../show/api";
import { Collaborators } from "./Collaborators";
import { loadProjects, useProjects } from "./api";

type Tab = ShowPart | "music" | "people";
const TABS: { id: Tab; label: string }[] = [
  { id: "basic", label: t("基本信息") },
  { id: "hosts", label: t("主持人") },
  { id: "music", label: t("片头片尾") },
  { id: "publish", label: t("发布") },
  { id: "people", label: t("协作者") },
];

const tabFromHash = (): Tab => {
  const m = /^#\/project\/([\w-]+)/.exec(window.location.hash)?.[1];
  return TABS.some((x) => x.id === m) ? (m as Tab) : "basic";
};

/** Who you are (for 「（你）」 and whether you manage this project). */
export function useMe(): string | null {
  const [me, setMe] = useState<string | null>(null);
  useEffect(() => {
    authApi.status().then((s) => setMe(s.email), () => setMe(null));
  }, []);
  return me;
}

/** #/project (项目设置): the project's name and show profile, hosts, default intro / outro, publishing
 *  and collaborators, one tab each (#/project/<tab>). Was 节目设置. */
export function ProjectSettings() {
  const [tab, setTab] = useState<Tab>(tabFromHash);
  const show = useShow();
  const sp = useProjects();
  const me = useMe();
  useEffect(() => {
    const on = () => setTab(tabFromHash());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  if (!show) return <PageLoading label={t("正在打开项目设置…")} shape="list" />;
  const cur = sp?.current;
  return (
    <main className="show-page prj-settings">
      <div className="home-hero">
        <h1>{t("项目设置")}</h1>
        <p className="muted">{t("这个项目的名字、主持人和默认做法。导入、LACUNA 剪辑、show notes 和海报都按这里来。")}</p>
      </div>
      <div className="prj-tabs" role="tablist" aria-label={t("项目设置")}>
        {TABS.filter((x) => x.id !== "people" || cur).map((x) => (
          <a
            key={x.id}
            role="tab"
            aria-selected={tab === x.id}
            className="prj-tab"
            href={`#/project/${x.id}`}
            data-testid={`project-tab-${x.id}`}
          >
            {x.label}
          </a>
        ))}
      </div>
      <section className="card" role="tabpanel">
        {(tab === "basic" || tab === "hosts" || tab === "publish") && (
          <ShowForm key={tab} show={show} parts={[tab]} onSaved={() => void loadProjects(true)} />
        )}
        {tab === "music" && <ProjectMusic />}
        {tab === "people" && cur && <Collaborators id={cur.id} me={me} manage={cur.role === "admin"} />}
      </section>
    </main>
  );
}

/** 片头片尾: the project's default opener and ending; an album's own replace them. */
function ProjectMusic() {
  const [view, setView] = useState<AlbumsView | null>(null);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    albumsApi.list().then(setView, (e) => setErr((e as Error).message));
    libraryApi.library().then((l) => setAssets(l.assets), () => setAssets([]));
  }, []);
  if (!view) return err ? <p className="error">{err}</p> : null;
  const pick = (role: "intro" | "outro", id: string) => {
    setSaved(false);
    albumsApi
      .projectMusic({ [role]: id })
      .then((v) => {
        setView(v);
        setSaved(true);
      })
      .catch((e) => setErr((e as Error).message));
  };
  const options = (kind: "intro" | "outro") => [...assets].sort((a, b) => Number(b.kind === kind) - Number(a.kind === kind));
  const overriding = view.albums.filter((a) => a.intro || a.outro);
  return (
    <div className="show-form" data-testid="project-music">
      {(["intro", "outro"] as const).map((role) => (
        <label className="show-field" key={role}>
          <span>{role === "intro" ? t("默认片头") : t("默认片尾")}</span>
          <select value={view.project[role]?.asset_id ?? ""} onChange={(e) => pick(role, e.target.value)} data-testid={`project-${role}`}>
            <option value="">{t("不用")}</option>
            {options(role).map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        </label>
      ))}
      <small className="muted">
        {t("新导入的剧集自动带上。专辑可以设自己的片头片尾，覆盖这里的。")}
        {!!overriding.length && ` ${t("现在用自己的片头片尾的专辑：{names}", { names: overriding.map((a) => a.name).join("、") })}`}
      </small>
      {!assets.length && (
        <p className="small muted">
          {t("素材库里还没有音乐。")} <a href="#/library">{t("去素材库添加")}</a>
        </p>
      )}
      {saved && <span className="ok small">{t("已保存")}</span>}
      {err && <p className="error small">{err}</p>}
    </div>
  );
}

/** #/invite (邀请协作, top bar): the same collaborators panel, on its own page. */
export function InvitePage() {
  const sp = useProjects();
  const me = useMe();
  if (sp === undefined) return <PageLoading label={t("正在打开…")} shape="list" />;
  const cur = sp?.current;
  if (!cur) return <main className="show-page"><p className="muted">{t("没有登录账号时不需要邀请协作。")}</p></main>;
  return (
    <main className="show-page prj-settings">
      <div className="home-hero">
        <h1>{t("邀请协作「{name}」", { name: cur.name })}</h1>
        <p className="muted">{t("只能邀请到项目这一层。对方剪的时候用对方自己的剪辑习惯。")}</p>
      </div>
      <section className="card">
        <Collaborators id={cur.id} me={me} manage={cur.role === "admin"} />
      </section>
      <p>
        <a className="btn btn-outline" href="#/">
          {t("完成")}
        </a>
      </p>
    </main>
  );
}
