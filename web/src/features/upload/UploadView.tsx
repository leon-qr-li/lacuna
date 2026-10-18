import { useEffect, useState } from "react";
import { api } from "../../api";
import { copyRich, copyText } from "../../markdown";
import type { PublishView } from "../publish/api";
import { publishApi } from "../publish/api";
import type { UploadView as View } from "./api";
import { uploadApi } from "./api";
import { fmtDateTime, joinList, t } from "../../i18n";
import { PageLoading } from "../loading/Loading";

const mb = (b: number) => `${(b / 1024 / 1024).toFixed(b >= 100 * 1024 * 1024 ? 0 : 1)} MB`;

/** 上传喜马拉雅: everything for the 喜马拉雅 upload form on one page, in the form's order. Leon uploads
 *  by hand (no upload API for personal creators); this page only gathers what other tabs made. */
export function UploadView({ id, version, flash }: { id: string; version: string; flash: (m: string) => void }) {
  const [view, setView] = useState<View | null>(null);
  const [pub, setPub] = useState<PublishView | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([uploadApi.upload(id), publishApi.publish(id)])
      .then(([u, p]) => {
        setView(u);
        setPub(p);
      })
      .catch((e) => setErr(String(e.message ?? e)));
  }, [id, version]);

  const copy = async (rich: boolean, text: string, msg: string) => {
    try {
      await (rich ? copyRich(text) : copyText(text));
      flash(msg);
    } catch (e) {
      flash(t("复制失败：{message}", { message: (e as Error).message }));
    }
  };

  // the browser download still happens (the link); this also puts the cover next to the WAV / MP3
  const saveCover = () => {
    uploadApi.saveCover(id).then(
      (r) => {
        setSaved(r.path);
        flash(t("封面已存到 {path}", { path: r.path }));
      },
      (e) => flash(t("封面没存进导出文件夹：{message}", { message: (e as Error).message })),
    );
  };

  if (err) return <p className="error pad">{t("上传页打不开：")}{err}</p>;
  if (!view || !pub) return <PageLoading label={t("正在打开上传页…")} />;

  const tab = (mode: string) => `#/ep/${encodeURIComponent(id)}/${mode}`;
  const pack = pub.pack;
  const missing = [!view.audio && "WAV", !pack && t("发布资料"), !view.cover && t("封面")].filter(Boolean) as string[];
  const stale = [view.audio?.stale && "WAV", pack?.stale && t("show notes 的时间戳")].filter(Boolean) as string[];

  return (
    <main className="upload">
      <div>
        <h1>{t("上传喜马拉雅")}</h1>
        <p className="muted small">
          {t("按喜马拉雅上传页的顺序排好了：下载音频、复制标题和简介、下载封面，你自己上传。小宇宙会从喜马拉雅自动同步。")}
        </p>
      </div>

      <div className={view.ready ? "card" : "banner-card"} role="status" data-testid="upload-summary">
        {view.ready ? (
          <span>{t("✓ 都准备好了。")}</span>
        ) : (
          <span>
            {missing.length > 0 && <>{t("还差：{list}。", { list: joinList(missing) })}</>}
            {stale.length > 0 && <>{t("剪辑后来又改过，{list}已经不是最新的。", { list: joinList(stale) })}</>}
          </span>
        )}{" "}
        <a href={view.upload_page} target="_blank" rel="noreferrer">
          {t("打开喜马拉雅创作中心 ↗")}
        </a>
      </div>

      <section className="card upload-step" aria-label={t("音频")}>
        <div className="card-head">
          <strong className="upload-h"><span className="step-n" aria-hidden="true">1</span>{t("音频（WAV）")}</strong>
        </div>
        {view.audio ? (
          <>
            <p className="mono small" data-testid="upload-wav">
              {view.audio.name} · {mb(view.audio.bytes)}
              {view.audio.exported_at ? t(" · 导出于 {p0}", { p0: fmtDateTime(view.audio.exported_at) }) : ""}
            </p>
            {view.audio.stale && <p className="warn small">{t("这个 WAV 是剪辑改动之前导出的。点上方的「导出」再导一次。")}</p>}
            <div className="row wrap gap8">
              <a className="btn btn-primary btn-small" href={uploadApi.wavUrl(id, view.audio.name)} download={view.audio.name}>
                {t("下载 WAV")}
              </a>
              <button
                type="button"
                className="btn btn-outline btn-small"
                onClick={() => api.openExports(id).then((r) => flash(t("已打开 {folder}", { folder: r.folder })), (e) => flash(t("打不开：{message}", { message: e.message })))}
              >
                {t("打开所在文件夹")}
              </button>
            </div>
          </>
        ) : (
          <p className="upload-missing">{t("还没导出 WAV。点上方的「导出」，勾上 WAV。")}</p>
        )}
      </section>

      <section className="card upload-step" aria-label={t("标题")}>
        <div className="card-head">
          <strong className="upload-h"><span className="step-n" aria-hidden="true">2</span>{t("标题")}</strong>
          {pack && (
            <button type="button" className="btn btn-outline btn-small" onClick={() => copy(false, pack.title, t("标题已复制"))}>
              {t("复制标题")}
            </button>
          )}
        </div>
        {pack ? (
          <p className="upload-title" data-testid="upload-title">
            {pack.title}
          </p>
        ) : (
          <p className="upload-missing">
            {t("还没有发布资料。去")} <a href={tab("publish")}>{t("发布资料")}</a> {t("生成。")}
          </p>
        )}
      </section>

      <section className="card upload-step" aria-label={t("简介")}>
        <div className="card-head">
          <strong className="upload-h"><span className="step-n" aria-hidden="true">3</span>{t("简介（show notes）")}</strong>
          {pack && (
            <span className="row wrap gap8">
              <button type="button" className="btn btn-primary btn-small" onClick={() => copy(true, pack.markdown, t("show notes 已复制（带格式），直接贴进简介框"))}>
                {t("复制 show notes")}
              </button>
              {pack.blurb && (
                <button type="button" className="btn btn-outline btn-small" onClick={() => copy(false, pack.blurb, t("一句话简介已复制"))}>
                  {t("复制一句话简介")}
                </button>
              )}
            </span>
          )}
        </div>
        {pack ? (
          <>
            {pack.blurb && <p data-testid="upload-blurb">{pack.blurb}</p>}
            {pack.stale && (
              <p className="warn small">
                {t("剪辑后来又改过，时间戳可能不准。去")} <a href={tab("publish")}>{t("发布资料")}</a> {t("点「更新时间戳」（本机算，不花钱）。")}
              </p>
            )}
            <p className="muted small">{t("想先改文字，去")} <a href={tab("publish")}>{t("发布资料")}</a> {t("编辑。")}</p>
          </>
        ) : (
          <p className="upload-missing">{t("生成发布资料后这里就能复制。")}</p>
        )}
      </section>

      <section className="card upload-step" aria-label={t("封面")}>
        <div className="card-head">
          <strong className="upload-h"><span className="step-n" aria-hidden="true">4</span>{t("封面")}</strong>
        </div>
        {view.cover ? (
          <div className="upload-cover-row">
            <img className="upload-cover" src={uploadApi.coverUrl(id, view.cover.rendered_at)} alt={t("本期封面")} />
            <div className="upload-col">
              <span className="muted small">
                {view.cover.px}×{view.cover.px} JPG · {mb(view.cover.bytes)}
              </span>
              <a
                className="btn btn-primary btn-small"
                href={uploadApi.coverUrl(id, view.cover.rendered_at)}
                download={`${id}_cover.jpg`}
                onClick={saveCover}
              >
                {t("下载封面")}
              </a>
              {saved && (
                <span className="muted small" data-testid="upload-cover-saved">
                  {t("也存到了导出文件夹，和音频放在一起：")}
                  <span className="mono upload-path">{saved}</span>
                </span>
              )}
            </div>
          </div>
        ) : (
          <p className="upload-missing">
            {t("还没选封面。去")} <a href={tab("poster")}>{t("海报")}</a> {t("画一版，点「用这张」。")}
          </p>
        )}
      </section>

      <p className="muted small">{t("最后在喜马拉雅上选专辑「洛城二三事」，确认后发布。")}</p>
    </main>
  );
}
