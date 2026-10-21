import { useEffect, useRef, useState } from "react";
import { t } from "../../i18n";
import { albumsApi, type AlbumsView } from "../albums/api";
import { authApi } from "../auth/api";
import { confirmDialog } from "../dialog/Dialog";
import { libraryApi, type Asset } from "../library/api";
import { PageLoading } from "../loading/Loading";
import { ShowForm, type ShowPart } from "../show/ShowForm";
import { useShow } from "../show/api";
import { spacesApi, type MySpace } from "../spaces/api";
import { ProjectAvatar } from "./Avatar";
import { Collaborators } from "./Collaborators";
import { loadProjects, setProjects, useProjects } from "./api";

type Tab = ShowPart | "music" | "people";
const TABS: { id: Tab; label: string }[] = [
  { id: "basic", label: t("基本信息") },
  { id: "hosts", label: t("主持人") },
  { id: "music", label: t("片头片尾") },
  { id: "publish", label: t("发布") },
  { id: "people", label: t("协作者") },
];

const ABOUT: Record<Tab, string> = {
  basic: t("节目的名字、图片、语言、介绍和专有名词。"),
  hosts: t("每位主持人一条分轨，最多 4 位。"),
  music: t("新剧集默认用的片头片尾。"),
  publish: t("show notes 和发布资料的默认做法。"),
  people: t("谁能看、谁能剪这个节目。"),
};

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
  if (!show) return <PageLoading label={t("正在打开节目设置…")} shape="list" />;
  const cur = sp?.current;
  return (
    <main className="home settings prj-settings">
      <div className="home-hero">
        <h1>{t("节目设置")}</h1>
        <p className="muted">{t("这个节目的名字、主持人和默认做法。导入、LACUNA 剪辑、show notes 和海报都按这里来。")}</p>
      </div>
      <div className="set-layout">
        <nav className="set-nav" aria-label={t("节目设置")}>
          {[{ g: t("基本"), ids: ["basic", "hosts", "music", "publish"] }, { g: t("团队"), ids: cur ? ["people"] : [] }].filter((x) => x.ids.length).map(({ g, ids }) => (
            <div className="set-nav-group" key={g}>
              <div className="set-nav-label">{g}</div>
              {TABS.filter((x) => ids.includes(x.id) && (x.id !== "people" || cur)).map((x) => (
                <a key={x.id} className="set-nav-item" href={`#/project/${x.id}`} aria-current={tab === x.id ? "page" : undefined} data-testid={`project-tab-${x.id}`}>
                  {x.label}
                </a>
              ))}
            </div>
          ))}
        </nav>
        <div className="set-main">
          <div className="set-head">
            <h2>{TABS.find((x) => x.id === tab)?.label}</h2>
            <p className="muted small">{ABOUT[tab]}</p>
          </div>
          {cur?.archived && <ArchivedNote p={cur} />}
          <section className="card" role="tabpanel">
            {tab === "basic" && cur && <ProjectLook p={cur} />}
            {(tab === "basic" || tab === "hosts" || tab === "publish") && (
              <ShowForm key={tab} show={show} parts={[tab]} onSaved={() => void loadProjects(true)} />
            )}
            {tab === "basic" && cur?.role === "admin" && !cur.archived && <ArchiveZone p={cur} />}
            {tab === "music" && <ProjectMusic />}
            {tab === "people" && cur && <Collaborators id={cur.id} me={me} manage={cur.role === "admin"} />}
          </section>
        </div>
      </div>
    </main>
  );
}

/** 基本信息, on top: the project's square picture (or its colour), for its managers to change. */
function ProjectLook({ p }: { p: MySpace }) {
  const file = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const manage = p.role === "admin" && !p.archived;
  const act = async (fn: () => Promise<Parameters<typeof setProjects>[0]>) => {
    setBusy(true);
    setErr(null);
    try {
      setProjects(await fn());
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="prj-look" data-testid="project-look">
      <ProjectAvatar p={p} size={88} />
      <div className="prj-look-body">
        <strong>{t("节目图片")}</strong>
        <span className="muted small">{t("方形图片，会自动裁成正方形。没有图片时用这个节目自己的颜色。")}</span>
        {manage && (
          <div className="prj-look-actions">
            <button type="button" className="btn btn-outline btn-small" disabled={busy} onClick={() => file.current?.click()} data-testid="project-picture-upload">
              {p.picture ? t("换一张图片") : t("上传图片")}
            </button>
            {p.picture && (
              <button type="button" className="btn btn-outline btn-small" disabled={busy} onClick={() => void act(() => spacesApi.dropPicture(p.id))} data-testid="project-picture-remove">
                {t("改用颜色")}
              </button>
            )}
            <input
              ref={file}
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif"
              hidden
              data-testid="project-picture-file"
              onChange={(e) => {
                const f = e.target.files?.[0];
                e.target.value = "";
                if (f) void act(() => spacesApi.setPicture(p.id, f));
              }}
            />
          </div>
        )}
        {err && <p className="error small">{err}</p>}
      </div>
    </div>
  );
}

/** 基本信息, at the bottom, for managers: archive the project (read-only, under 已归档). */
function ArchiveZone({ p }: { p: MySpace }) {
  const [err, setErr] = useState<string | null>(null);
  const archive = async () => {
    const ok = await confirmDialog({
      title: t("归档「{name}」？", { name: p.name }),
      message: t("归档后节目移到「已归档」，所有协作者都只能查看、不能修改。随时可以恢复。"),
      confirmLabel: t("归档"),
    });
    if (!ok) return;
    try {
      setProjects(await spacesApi.archive(p.id, true));
    } catch (e) {
      setErr((e as Error).message);
    }
  };
  return (
    <div className="prj-danger-zone">
      <div>
        <strong>{t("归档节目")}</strong>
        <p className="muted small">{t("不再做的节目可以归档：只读，放进「已归档」。永久删除要先归档。")}</p>
        {err && <p className="error small">{err}</p>}
      </div>
      <button type="button" className="btn btn-outline" onClick={() => void archive()} data-testid="project-archive-btn">
        {t("归档")}
      </button>
    </div>
  );
}

/** An archived project's settings: say why nothing can change, and let a manager restore it here. */
function ArchivedNote({ p }: { p: MySpace }) {
  const [err, setErr] = useState<string | null>(null);
  return (
    <div className="prj-readonly" data-testid="project-readonly">
      <span>{t("这个节目已归档，只能查看。恢复后才能修改。")}</span>
      {p.role === "admin" && (
        <button
          type="button"
          className="btn btn-outline btn-small"
          onClick={() => spacesApi.archive(p.id, false).then(setProjects, (e) => setErr((e as Error).message))}
          data-testid="project-unarchive"
        >
          {t("恢复")}
        </button>
      )}
      {err && <span className="error small">{err}</span>}
    </div>
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
        <p className="muted">{t("只能邀请到节目这一层。对方剪的时候用对方自己的剪辑习惯。")}</p>
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
