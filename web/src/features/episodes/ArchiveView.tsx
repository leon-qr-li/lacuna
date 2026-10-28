import { useCallback, useEffect, useState } from "react";
import { fmtDateTime, t } from "../../i18n";
import { PageLoading } from "../loading/Loading";
import { confirmDialog } from "../dialog/Dialog";
import { EpisodeCard } from "./EpisodeCard";
import { episodesApi, type ArchivedItem } from "./api";
import { EmptyState } from "../states/States";
import { useReadOnly } from "../listen-only/state";

const mb = (b: number) => (b >= 1e9 ? `${(b / 1e9).toFixed(1)} GB` : `${Math.max(Math.round(b / 1e6), 0)} MB`);

/** 已归档 (#/archive): archived episodes, each restorable or deletable for good (首检 #3). */
export function ArchiveView() {
  const [list, setList] = useState<ArchivedItem[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const ro = useReadOnly() !== null; // 只听 or an archived show: no 恢复 / 永久删除 (the server refuses them)
  const load = useCallback(() => {
    episodesApi
      .archived()
      .then((r) => setList(r.episodes))
      .catch((e) => setErr(String((e as Error).message ?? e)));
  }, []);
  useEffect(load, [load]);
  const restore = (e: ArchivedItem) =>
    episodesApi
      .restore(e.id)
      .then(() => {
        setNote(t("「{title}」已恢复到剧集列表", { title: e.title }));
        load();
      })
      .catch((x) => setErr((x as Error).message));
  const remove = async (e: ArchivedItem) => {
    const ok = await confirmDialog({
      title: t("永久删除「{title}」？", { title: e.title }),
      message:
        t("会删掉这一集的剪辑、对话记录、发布资料、封面、上传的原始音轨，以及只属于这一集的素材。这一步不能撤销。") +
        "\n" +
        t("学到的习惯和规则都会保留，公共素材和别的剧集也在用的素材也留着。你电脑上原来的录音文件不受影响。删除前请先下载需要的导出成品。"),
      confirmLabel: t("永久删除"),
      danger: true,
    });
    if (!ok) return;
    setBusy(e.id);
    setErr(null);
    try {
      const r = await episodesApi.remove(e.id);
      setNote(
        t("「{title}」已永久删除，腾出 {size}。学到的习惯都还在。", { title: e.title, size: mb(r.freed_bytes) }) +
          (r.assets?.length ? t("一起删掉了 {n} 个本集素材：{names}", { n: r.assets.length, names: r.assets.join("、") }) : ""),
      );
      load();
    } catch (x) {
      setErr((x as Error).message);
    } finally {
      setBusy(null);
    }
  };
  if (!list && !err) return <PageLoading label={t("正在打开已归档…")} shape="list" />;
  return (
    <main className="home archive">
      <div className="home-hero">
        <h1>{t("已归档")}</h1>
        <p className="muted">{t("归档的剧集不在剧集列表里显示，文件都还在。可以恢复，也可以永久删除；学到的习惯永远保留。")}</p>
      </div>
      {note && (
        <p className="ep-note" role="status">
          {note}
        </p>
      )}
      {err && <p className="error">{err}</p>}
      {list?.length === 0 && (
        <EmptyState
          icon="▢"
          title={t("没有归档的剧集")}
          text={t("归档的剧集会放在这里，随时可以恢复。")}
          action={
            <a className="btn btn-outline btn-small linkbtn" href="#/">
              {t("回首页")}
            </a>
          }
          testid="archive-empty"
        />
      )}
      <ul className="ep-list">
        {list?.map((e) => (
          <EpisodeCard
            key={e.id}
            e={e}
            extra={
              <>
                <span className="muted small">{t("归档于 {at}", { at: fmtDateTime(e.archived_at) })}</span>
                {!ro && (
                <span className="ep-tile-actions">
                  <button type="button" className="btn btn-outline btn-small" onClick={() => void restore(e)}>
                    {t("恢复")}
                  </button>
                  <button type="button" className="btn btn-small btn-danger-outline" disabled={busy === e.id} onClick={() => void remove(e)}>
                    {t("永久删除")}
                  </button>
                </span>
                )}
              </>
            }
          />
        ))}
      </ul>
    </main>
  );
}
