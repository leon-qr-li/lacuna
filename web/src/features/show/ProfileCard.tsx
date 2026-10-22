import { useState } from "react";
import { t } from "../../i18n";
import { useAlbums } from "../albums/api";
import { useProjects } from "../projects/api";
import { markDone, useOnboarding } from "../onboarding/api";
import { setShow, showApi, useShow, type Show } from "./api";

const splitNames = (s: string) =>
  s
    .split(/[\n,，、;；]+/)
    .map((x) => x.trim())
    .filter(Boolean);

/** 节目资料卡 (C6, new-user batch): on a new show's 首页, three things that help LACUNA cut it better, each filled
 *  in place: a one-line description, names that come up a lot, the opener and ending. Ticked once filled; gone
 *  when all are, or after 不用了 (per show, for this person). The same fields stay in 节目设置. */
export function ProfileCard({ show, episodes }: { show: Show | null; episodes: number }) {
  const ob = useOnboarding();
  const cur = useProjects()?.current;
  const albums = useAlbums();
  const [open, setOpen] = useState<"about" | "terms" | null>(null);
  const [text, setText] = useState("");
  const [err, setErr] = useState<string | null>(null);
  if (!show || show.needs_setup || !cur || cur.sample || cur.role === "viewer" || !ob || !albums.view) return null;
  const off = `card.${cur.id}`;
  if (ob.done.includes(off) || episodes >= 3) return null;
  const music = !!albums.view.project.intro && !!albums.view.project.outro;
  const have = { about: !!show.about.trim(), terms: !!show.terms?.length, music };
  if (have.about && have.terms && have.music) return null;
  const save = async (patch: Partial<Show>) => {
    try {
      const { show_name, about, language, footer, hosts, publish, terms, rev } = { ...show, ...patch };
      setShow(await showApi.save({ show_name, about, language, footer, hosts, publish, terms, rev }));
      setOpen(null);
      setErr(null);
    } catch (e) {
      setErr((e as Error).message);
    }
  };
  const edit = (k: "about" | "terms") => {
    setOpen(k);
    setText(k === "about" ? show.about : (show.terms ?? []).join("、"));
  };
  const item = (k: "about" | "terms", label: string, hint: string) => (
    <li className={have[k] ? "is-done" : ""}>
      <span className="onboard-tick" aria-hidden="true">{have[k] ? "✓" : ""}</span>
      {open === k ? (
        <form
          className="grow row gap8 profile-edit"
          onSubmit={(e) => {
            e.preventDefault();
            void save(k === "about" ? { about: text } : { terms: splitNames(text) });
          }}
        >
          <input
            className="grow"
            value={text}
            onChange={(e) => setText(e.target.value)}
            maxLength={k === "about" ? 200 : 2000}
            placeholder={hint}
            aria-label={label}
            autoFocus
            data-testid={`profile-${k}-input`}
          />
          <button type="submit" className="btn btn-primary btn-small">
            {t("保存")}
          </button>
          <button type="button" className="btn btn-ghost btn-small" onClick={() => setOpen(null)}>
            {t("取消")}
          </button>
        </form>
      ) : (
        <button type="button" className="linkbtn grow profile-item" onClick={() => edit(k)} data-testid={`profile-${k}`}>
          {label}
          <span className="muted small onboard-hint">{have[k] ? (k === "about" ? show.about : (show.terms ?? []).join("、")) : hint}</span>
        </button>
      )}
    </li>
  );
  return (
    <section className="card profile-card" aria-label={t("节目资料卡")} data-testid="profile-card">
      <div className="card-head">
        <h2>{t("让 LACUNA 更懂这个节目")}</h2>
        <button type="button" className="btn btn-ghost btn-small" onClick={() => markDone(off)} data-testid="profile-off">
          {t("不用了")}
        </button>
      </div>
      <ol className="onboard-steps">
        {item("about", t("一句话简介"), t("这个节目聊什么，比如「两位主持人聊刚看过的电影」"))}
        {item("terms", t("常提到的名字"), t("人名、片名、品牌，用顿号或逗号隔开；文字稿会照这个写法"))}
        <li className={music ? "is-done" : ""}>
          <span className="onboard-tick" aria-hidden="true">{music ? "✓" : ""}</span>
          <a className="grow profile-item" href="#/project" data-testid="profile-music">
            {t("片头片尾音乐")}
            <span className="muted small onboard-hint">{t("在节目设置里选好，每一集都会自动放上")}</span>
          </a>
        </li>
      </ol>
      {err && <p className="error small">{err}</p>}
    </section>
  );
}

/** On the import form while the show has no description: one quiet line, never in the way. */
export function AboutHint() {
  const show = useShowAbout();
  if (show !== "") return null;
  return <p className="muted small" data-testid="about-hint">{t("提示：在首页的节目资料卡里写一句节目简介，LACUNA 剪第一刀时会更懂这个节目。")}</p>;
}

function useShowAbout(): string | null {
  const s = useShow();
  return s && !s.needs_setup ? s.about.trim() : null;
}
