import { useState } from "react";
import type { ReactNode } from "react";
import type { RequestError } from "../../api";
import { lang as uiLang, t } from "../../i18n";
import { noticeDialog } from "../dialog/Dialog";
import { BusyLabel } from "../loading/Loading";
import { AUTO_PUBLISH, AUTO_PUBLISH_LABELS, LANGUAGE_LABELS, LANGUAGES, setShow, showApi, type AutoPublish, type CutAdjust, type Host, type HostColor, type Language, type Show } from "./api";
import { openFeedback } from "../feedback/bus";

const COLOR_LABELS: Record<HostColor, string> = {
  blue: t("蓝"),
  purple: t("紫"),
  teal: t("青"),
  amber: t("琥珀"),
  green: t("绿"),
  pink: t("粉"),
};
const ADJUST_LABELS: Record<CutAdjust, string> = {
  more: t("比我平时更狠"),
  same: t("和我平时一样"),
  less: t("比我平时更松"),
};
const ADJUSTS: CutAdjust[] = ["more", "same", "less"];

const newHost = (s: Show, hosts: Host[]): Host => ({
  tag: "",
  name: "",
  color: s.colors.find((c) => !hosts.some((h) => h.color === c)) ?? s.colors[0],
  cut_adjust: "same",
  style: "",
});

/** 专有名词 as typed (lines, commas, 、) -> the list the server keeps */
const splitTerms = (s: string) =>
  s
    .split(/[\n,，、;；]+/)
    .map((x) => x.trim())
    .filter(Boolean);

/** What a recording has to be: one file per host (said on the first setup and on every import). */
export function TrackNote() {
  return (
    <small className="muted" data-testid="track-note">
      {t("LACUNA 需要每位主持人单独一条录音。Riverside、Zencastr 的分轨下载，或 Zoom 的「为每位参与者单独录制音频」都可以。")}
    </small>
  );
}

/** The show's name and hosts (+ in full mode: editing style, show-notes footer, 喜马拉雅). `compact`
 *  is the first-run setup of a new workspace: only what an import needs. */
export type ShowPart = "basic" | "hosts" | "publish";

/** `parts`: which tabs of 项目设置 this form shows (all by default); the save sends everything. */
/** `extra`: more fields above the save button (the first-run setup's optional questions, features/feedback). */
export function ShowForm({ show, compact, onSaved, parts, extra }: { show: Show; compact?: boolean; onSaved?: (s: Show) => void; parts?: ShowPart[]; extra?: ReactNode }) {
  const has = (p: ShowPart) => !parts || parts.includes(p);
  const [name, setName] = useState(show.show_name);
  const [about, setAbout] = useState(show.about);
  // a show nobody has set up yet speaks the interface's language (an English user gets English recognition)
  const [language, setLanguage] = useState<Language>(compact && !show.hosts.length ? uiLang : (show.language ?? "zh"));
  const [footer, setFooter] = useState(show.footer);
  const [hosts, setHosts] = useState<Host[]>(show.hosts.length ? show.hosts : [newHost(show, [])]);
  const [album, setAlbum] = useState(show.publish.album);
  const [wish, setWish] = useState<AutoPublish[]>(show.publish.auto_wish ?? []);
  // 专有名词: one per line (or comma separated); hints for the transcript's proofreading, the audio wins
  const [terms, setTerms] = useState((show.terms ?? []).join("\n"));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  // the version this form was filled from (co-editing: a save from an older one is refused)
  const [rev, setRev] = useState(show.rev);

  /** Fill the form with what is stored (after someone else saved first). */
  const fill = (s: Show) => {
    setName(s.show_name);
    setAbout(s.about);
    setLanguage(s.language ?? "zh");
    setFooter(s.footer);
    setHosts(s.hosts.length ? s.hosts : [newHost(s, [])]);
    setAlbum(s.publish.album);
    setWish(s.publish.auto_wish ?? []);
    setTerms((s.terms ?? []).join("\n"));
    setRev(s.rev);
  };

  const edit = (i: number, patch: Partial<Host>) => {
    setSaved(false);
    setHosts((hs) => hs.map((h, j) => (j === i ? { ...h, ...patch } : h)));
  };
  const save = async () => {
    setBusy(true);
    setErr(null);
    try {
      const s = await showApi.save({
        show_name: name,
        about,
        language,
        footer,
        hosts,
        // where the show is published stays as stored (no picker since 自动发布 即将推出, 2026-10-23)
        publish: { ximalaya: show.publish.ximalaya, album, auto_wish: compact ? (show.publish.auto_wish ?? []) : wish },
        ...(compact ? {} : { terms: splitTerms(terms) }),
        rev,
      });
      setShow(s);
      setHosts(s.hosts);
      setTerms((s.terms ?? []).join("\n"));
      setRev(s.rev);
      setSaved(true);
      onSaved?.(s);
    } catch (e) {
      if ((e as RequestError).stale) {
        // someone else saved first (features/coedit): show what is stored now, nothing was overwritten
        try {
          const s = await showApi.get();
          setShow(s);
          fill(s);
        } catch {
          /* the notice still says what happened */
        }
        await noticeDialog((e as Error).message);
        return;
      }
      setErr(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form
      className="show-form"
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
      onChange={() => setSaved(false)}
    >
      {has("basic") && (
        <>
          <label className="show-field">
            <span>{t("节目名")}</span>
            <input value={name} maxLength={80} onChange={(e) => setName(e.target.value)} placeholder={t("比如：周末电影院")} data-testid="show-name" />
          </label>
          <label className="show-field">
            <span>{t("语言")}</span>
            <select value={language} onChange={(e) => setLanguage(e.target.value as Language)} data-testid="show-language">
              {LANGUAGES.map((l) => (
                <option key={l} value={l}>
                  {LANGUAGE_LABELS[l]}
                </option>
              ))}
            </select>
            <small className="muted">{t("主持人说的语言。决定用哪个语音识别和剪辑方式；导入时每集还能单独改。")}</small>
          </label>
        </>
      )}
      {!compact && has("basic") && (
        <label className="show-field">
          <span>{t("一句话介绍")}</span>
          <input value={about} maxLength={200} onChange={(e) => setAbout(e.target.value)} placeholder={t("比如：两个朋友的电影闲聊")} />
          <small className="muted">{t("AI 剪辑、写 show notes 和画海报时会参考。")}</small>
        </label>
      )}
      {!compact && has("basic") && (
        <label className="show-field">
          <span>{t("专有名词")}</span>
          <textarea
            value={terms}
            rows={3}
            onChange={(e) => setTerms(e.target.value)}
            placeholder={t("一行一个，比如：王家卫、花样年华、PULSE")}
            data-testid="show-terms"
          />
          <small className="muted">{t("节目里常说的人名、片名、栏目名。文字稿听错成发音相近的字时按这里改；以录音为准，发音不像的不会硬改。")}</small>
        </label>
      )}
      {has("hosts") && (
        <div className="show-field">
          <span>{t("主持人（每人一条分轨）")}</span>
          {compact && <TrackNote />}
          <ul className="show-hosts">
            {hosts.map((h, i) => (
              <li key={h.tag || `new-${i}`} className="show-host" data-testid="show-host">
                <div className="show-host-top">
                  <span className="host-dot" style={{ background: `var(--c-${h.color})` }} aria-hidden />
                  <input
                    value={h.name}
                    maxLength={40}
                    onChange={(e) => edit(i, { name: e.target.value })}
                    placeholder={t("名字")}
                    aria-label={t("第 {n} 位主持人的名字", { n: i + 1 })}
                  />
                  <div className="show-swatches" role="group" aria-label={t("颜色")}>
                    {show.colors.map((c) => (
                      <button
                        key={c}
                        type="button"
                        className={`show-swatch c-${c}`}
                        aria-pressed={h.color === c}
                        aria-label={COLOR_LABELS[c]}
                        title={COLOR_LABELS[c]}
                        onClick={() => edit(i, { color: c })}
                      />
                    ))}
                  </div>
                  {hosts.length > 1 && (
                    <button
                      type="button"
                      className="btn btn-ghost btn-small"
                      onClick={() => setHosts((hs) => hs.filter((_, j) => j !== i))}
                      aria-label={t("去掉 {name}", { name: h.name || t("这位主持人") })}
                    >
                      {t("去掉")}
                    </button>
                  )}
                </div>
                {!compact && (
                  <>
                    <label className="row gap8 wrap">
                      <span className="small muted">{t("剪辑力度")}</span>
                      <select value={h.cut_adjust} onChange={(e) => edit(i, { cut_adjust: e.target.value as CutAdjust })} data-testid="host-adjust">
                        {ADJUSTS.map((l) => (
                          <option key={l} value={l}>
                            {ADJUST_LABELS[l]}
                          </option>
                        ))}
                      </select>
                      <a className="small" href="#/settings/edit">
                        {t("我平时的剪辑力度")}
                      </a>
                    </label>
                    <textarea
                      value={h.style}
                      maxLength={500}
                      onChange={(e) => edit(i, { style: e.target.value })}
                      placeholder={t("给 AI 的剪辑要求（可不填），比如：保留她的口头禅，跑题的长段可以删")}
                      aria-label={t("{name} 的剪辑要求", { name: h.name || t("这位主持人") })}
                    />
                  </>
                )}
              </li>
            ))}
          </ul>
          {hosts.length < show.max_hosts ? (
            <div>
              <button type="button" className="btn btn-outline btn-small" onClick={() => setHosts((hs) => [...hs, newHost(show, hs)])}>
                {t("+ 加一位主持人")}
              </button>
            </div>
          ) : (
            <small className="muted" data-testid="show-hosts-max">
              {t("每个节目最多 {n} 位主持人（每人一条分轨）。", { n: show.max_hosts })}
            </small>
          )}
          {!compact && <small className="muted">{t("改名字不影响已经导入的剧集；新导入的剧集用新名字。")}</small>}
        </div>
      )}
      {!compact && has("publish") && (
        <>
          <label className="show-field">
            <span>{t("show notes 结尾")}</span>
            <textarea value={footer} maxLength={600} onChange={(e) => setFooter(e.target.value)} placeholder={t("每期 show notes 最后的一段话（可不填）")} />
          </label>
          <fieldset className="show-field show-auto-publish" data-testid="show-auto-publish">
            <legend>{t("自动发布")}</legend>
            <div className="row gap8 auto-publish-head">
              <span className="soon-badge">{t("即将推出")}</span>
              <span>{t("以后可以从 LACUNA 一键发布到播客平台。")}</span>
            </div>
            <small className="muted">{t("你想自动发到哪些平台？（可多选，帮我们决定先做哪个）")}</small>
            <div className="row gap8 wrap">
              {AUTO_PUBLISH.map((p) => (
                <label key={p} className="check">
                  <input
                    type="checkbox"
                    checked={wish.includes(p)}
                    onChange={(e) => {
                      setSaved(false);
                      setWish((ws) => (e.target.checked ? AUTO_PUBLISH.filter((x) => x === p || ws.includes(x)) : ws.filter((x) => x !== p)));
                    }}
                    data-testid={`auto-publish-${p}`}
                  />
                  {AUTO_PUBLISH_LABELS[p]}
                </label>
              ))}
            </div>
            <small className="muted">
              {t("想要的平台不在这里？")}{" "}
              <a
                href="#"
                onClick={(e) => {
                  e.preventDefault();
                  openFeedback({ kind: "idea", source: "publish", platforms: wish.map((p) => AUTO_PUBLISH_LABELS[p]) });
                }}
                data-testid="auto-publish-feedback"
              >
                {t("告诉我们")}
              </a>
            </small>
          </fieldset>
          {show.publish.ximalaya && (
            <label className="show-field">
              <span>{t("喜马拉雅专辑名")}</span>
              <input value={album} maxLength={80} onChange={(e) => setAlbum(e.target.value)} placeholder={t("用喜马拉雅发布时填，「上传喜马拉雅」页会提醒你选这个专辑")} />
            </label>
          )}
        </>
      )}
      {extra}
      {err && <p className="error">{err}</p>}
      <div className="show-actions">
        <button type="submit" className="btn btn-primary" disabled={busy} data-testid="show-save">
          <BusyLabel busy={busy} label={compact ? t("开始使用") : t("保存")} busyLabel={t("保存中…")} />
        </button>
        {saved && !compact && <span className="ok small">{t("已保存")}</span>}
      </div>
    </form>
  );
}
