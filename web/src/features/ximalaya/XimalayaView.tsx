import { useEffect, useMemo, useState } from "react";
import { copyText } from "../../markdown";
import { t } from "../../i18n";
import { PageLoading } from "../loading/Loading";
import type { XimalayaStyleId, XimalayaView as View } from "./api";
import { ximalayaApi } from "./api";
import { EmptyState } from "../states/States";

// ".v2": a choice remembered while 杂志 was the default is dropped once, so everyone starts on 片场
// (Leon, 2026-10-18); a style picked from now on is remembered again
const KEY = "lacuna.ximalaya.style.v2";
const IDS: XimalayaStyleId[] = ["magazine", "cinema", "cards"];

/** 片场 is the default style (Leon, 2026-10-18); a style picked before is remembered. */
function remembered(): XimalayaStyleId {
  try {
    const v = localStorage.getItem(KEY);
    return IDS.includes(v as XimalayaStyleId) ? (v as XimalayaStyleId) : "cinema";
  } catch {
    return "cinema";
  }
}

/** Rich text for the editor and the same words as plain text, so either kind of paste works. */
async function copyBoth(html: string, text: string): Promise<void> {
  if (typeof ClipboardItem !== "undefined" && navigator.clipboard?.write) {
    await navigator.clipboard.write([
      new ClipboardItem({
        "text/html": new Blob([html], { type: "text/html" }),
        "text/plain": new Blob([text], { type: "text/plain" }),
      }),
    ]);
    return;
  }
  await copyText(text);
}

/** 喜马拉雅版: the show notes in three layouts the 喜马拉雅 description editor takes as they are
 *  (no tables or lists, a line per paragraph, every timeline line starting with its timestamp). */
export function XimalayaView({ id, version, flash }: { id: string; version: string; flash: (m: string) => void }) {
  const [view, setView] = useState<View | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [style, setStyle] = useState<XimalayaStyleId>(remembered);
  const [stamp, setStamp] = useState(() => String(Date.now()));

  useEffect(() => {
    let live = true;
    ximalayaApi
      .get(id)
      .then((v) => {
        if (!live) return;
        setView(v);
        setStamp(String(Date.now()));
      })
      .catch((e) => live && setErr(String(e.message ?? e)));
    return () => {
      live = false;
    };
  }, [id, version]);

  const pick = (s: XimalayaStyleId) => {
    setStyle(s);
    try {
      localStorage.setItem(KEY, s);
    } catch {
      /* private window: just don't remember */
    }
  };

  const cur = view?.styles?.[style] ?? null;
  // the preview shows the real images where the copied text has an 【插图】 line
  const preview = useMemo(
    () =>
      cur
        ? cur.html.replace(/<p data-img="([^"]+)">[^<]*<\/p>/g, (_m, name: string) => `<p class="xmly-img"><img src="${ximalayaApi.image(id, name, stamp)}" alt=""></p>`)
        : "",
    [cur, id, stamp],
  );

  if (err) return <p className="error pad">{t("喜马拉雅版打不开：")}{err}</p>;
  if (!view) return <PageLoading label={t("正在排版…")} />;

  const names: Record<XimalayaStyleId, [string, string]> = {
    magazine: [t("杂志"), t("纯文字：标题、引用和分割线，留白多，最稳妥")],
    cinema: [t("片场"), t("像电影的片头和片尾字幕：英文小标题、▍和 ◆ 记号")],
    cards: [t("图文"), t("顶上一张标题横幅，电影列表做成一张卡片，其余是文字")],
  };
  const copy = async (rich: boolean) => {
    if (!cur) return;
    try {
      await (rich ? copyBoth(cur.html, cur.text) : copyText(cur.text));
      flash(cur.images.length ? t("已复制。贴进简介框后，把【插图】那几行换成下面的图片") : t("已复制，直接贴进喜马拉雅的简介框"));
    } catch (e) {
      flash(t("复制失败：{message}", { message: (e as Error).message }));
    }
  };
  const label = (name: string) => (name === "banner.png" ? t("标题横幅") : t("本期提到的电影"));

  return (
    <main className="xmly">
      <div>
        <h1 className="step-title">{t("喜马拉雅版")}</h1>
        <p className="muted small">
          {t("把 show notes 排成喜马拉雅简介编辑器能直接用的样子：不用表格，一段一行，时间戳都在行首，在喜马拉雅和小宇宙里都能点。选一版，复制，贴进简介框。")}
        </p>
      </div>

      {!view.styles ? (
        <EmptyState
          icon="✎"
          title={t("还没有发布资料")}
          text={t("喜马拉雅版是从发布资料排出来的。")}
          action={
            <a className="btn btn-primary btn-small linkbtn" href={`#/ep/${encodeURIComponent(id)}/publish`}>
              {t("去生成发布资料")}
            </a>
          }
          testid="xmly-empty"
        />
      ) : (
        <>
          {view.stale && (
            <p className="card warn small" data-testid="xmly-stale">
              {t("剪辑后来又改过，时间戳可能不准。先去")} <a href={`#/ep/${encodeURIComponent(id)}/publish`}>{t("发布资料")}</a> {t("点「更新时间戳」。")}
            </p>
          )}
          {view.notes.map((n) => (
            <p key={n} className="muted small">
              {n}
            </p>
          ))}

          <div className="xmly-styles" role="radiogroup" aria-label={t("排版样式")}>
            {IDS.map((s) => (
              <button
                key={s}
                type="button"
                role="radio"
                aria-checked={style === s}
                className={`xmly-style${style === s ? " on" : ""}`}
                data-testid={`xmly-style-${s}`}
                onClick={() => pick(s)}
              >
                <strong>{names[s][0]}</strong>
                <span className="muted small">{names[s][1]}</span>
              </button>
            ))}
          </div>

          <div className="row wrap gap8">
            <button type="button" className="btn btn-primary" onClick={() => copy(true)} data-testid="xmly-copy">
              {t("复制这一版（带格式）")}
            </button>
            <button type="button" className="btn btn-outline" onClick={() => copy(false)}>
              {t("复制纯文本")}
            </button>
          </div>

          {cur && cur.images.length > 0 && (
            <section className="card" aria-label={t("配图")}>
              <div className="card-head">
                <strong>{t("配图")}</strong>
                <span className="muted small">{t("编辑器贴不进图片：贴好文字后，在【插图】那一行用编辑器的图片按钮上传这张图，再删掉那一行。")}</span>
              </div>
              <div className="xmly-images">
                {cur.images.map((name) => (
                  <figure key={name}>
                    <img src={ximalayaApi.image(id, name, stamp)} alt={label(name)} />
                    <figcaption className="row wrap gap8">
                      <span className="grow">{label(name)} · <span className="mono small">{name}</span></span>
                      <a className="btn btn-outline btn-small" href={ximalayaApi.image(id, name, stamp)} download={name}>
                        {t("下载")}
                      </a>
                    </figcaption>
                  </figure>
                ))}
              </div>
            </section>
          )}

          <section className="card" aria-label={t("预览")}>
            <div className="card-head">
              <strong>{t("预览")}</strong>
              <span className="muted small">{t("大致是贴进喜马拉雅后的样子，以喜马拉雅里实际显示为准")}</span>
            </div>
            <article className="xmly-preview" data-testid="xmly-preview" dangerouslySetInnerHTML={{ __html: preview }} />
          </section>
        </>
      )}
    </main>
  );
}
