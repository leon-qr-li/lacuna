import { useState } from "react";
import { t } from "../../i18n";
import { BusyLabel } from "../loading/Loading";
import { LANGUAGE_LABELS, LANGUAGES, setShow, showApi, type CutLevel, type Host, type HostColor, type Language, type Show } from "./api";

const COLOR_LABELS: Record<HostColor, string> = {
  blue: t("蓝"),
  purple: t("紫"),
  teal: t("青"),
  amber: t("琥珀"),
  green: t("绿"),
  pink: t("粉"),
};
const LEVEL_LABELS: Record<CutLevel, string> = {
  gentle: t("轻剪：多保留原话"),
  normal: t("正常"),
  firm: t("狠剪：啰嗦和跑题多删"),
};

const newHost = (s: Show, hosts: Host[]): Host => ({
  tag: "",
  name: "",
  color: s.colors.find((c) => !hosts.some((h) => h.color === c)) ?? s.colors[0],
  cut_level: "normal",
  style: "",
});

/** The show's name and hosts (+ in full mode: editing style, show-notes footer, 喜马拉雅). `compact`
 *  is the first-run setup of a new workspace: only what an import needs. */
export type ShowPart = "basic" | "hosts" | "publish";

/** `parts`: which tabs of 项目设置 this form shows (all by default); the save sends everything. */
export function ShowForm({ show, compact, onSaved, parts }: { show: Show; compact?: boolean; onSaved?: (s: Show) => void; parts?: ShowPart[] }) {
  const has = (p: ShowPart) => !parts || parts.includes(p);
  const [name, setName] = useState(show.show_name);
  const [about, setAbout] = useState(show.about);
  const [language, setLanguage] = useState<Language>(show.language ?? "zh");
  const [footer, setFooter] = useState(show.footer);
  const [hosts, setHosts] = useState<Host[]>(show.hosts.length ? show.hosts : [newHost(show, [])]);
  const [album, setAlbum] = useState(show.publish.album);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

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
        publish: { ximalaya: show.publish.ximalaya || !!album.trim(), album },
      });
      setShow(s);
      setHosts(s.hosts);
      setSaved(true);
      onSaved?.(s);
    } catch (e) {
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
            <span>{t("项目名")}</span>
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
      {has("hosts") && (
        <div className="show-field">
          <span>{t("主持人（每人一条分轨）")}</span>
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
                      <select value={h.cut_level} onChange={(e) => edit(i, { cut_level: e.target.value as CutLevel })}>
                        {show.cut_levels.map((l) => (
                          <option key={l} value={l}>
                            {LEVEL_LABELS[l]}
                          </option>
                        ))}
                      </select>
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
          {hosts.length < show.max_hosts && (
            <div>
              <button type="button" className="btn btn-outline btn-small" onClick={() => setHosts((hs) => [...hs, newHost(show, hs)])}>
                {t("+ 加一位主持人")}
              </button>
            </div>
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
          <label className="show-field">
            <span>{t("喜马拉雅专辑名")}</span>
            <input value={album} maxLength={80} onChange={(e) => setAlbum(e.target.value)} placeholder={t("用喜马拉雅发布时填，「上传喜马拉雅」页会提醒你选这个专辑")} />
          </label>
        </>
      )}
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
