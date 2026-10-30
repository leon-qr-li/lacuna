// 自动铺底 on the 配乐 page: tick songs, they go in a random order into every free stretch of talk, as a suggestion
import { useEffect, useState } from "react";
import { fmt } from "../../api";
import { t } from "../../i18n";
import { useListenOnly } from "../listen-only/state";
import type { MusicView } from "../library/api";
import { autobedApi, type AutoBedView } from "./api";
import "./autobed.css";

export function AutoBed({ id, version, onRun }: { id: string; version: string; onRun: (p: Promise<MusicView>) => void }) {
  const ro = useListenOnly();
  const [open, setOpen] = useState(false);
  const [v, setV] = useState<AutoBedView | null>(null);
  const [picked, setPicked] = useState<Set<string> | null>(null);

  useEffect(() => {
    if (!open) return;
    let live = true;
    autobedApi.view(id).then((x) => {
      if (!live) return;
      setV(x);
      // default: what is marked 聊天背景音 and not used yet, or what the current 自动铺底 uses
      setPicked((p) => p ?? new Set(x.songs.filter((s) => s.in_bed || (s.kind === "bed" && !s.used_as)).map((s) => s.id)));
    }, () => live && setV({ songs: [], free_s: 0, stretches: 0 }));
    return () => {
      live = false;
    };
  }, [id, open, version]);

  const toggle = (sid: string) =>
    setPicked((p) => {
      const n = new Set(p);
      if (n.has(sid)) n.delete(sid);
      else n.add(sid);
      return n;
    });
  const chosen = v?.songs.filter((s) => picked?.has(s.id)) ?? [];
  const total = chosen.reduce((a, s) => a + s.duration_s, 0);
  const done = v?.songs.some((s) => s.in_bed);

  if (!open)
    return (
      <div className="card banner-card autobed-banner">
        <span className="grow small">{t("给片头、片尾、间隙之外说话的地方随机铺上背景音乐。")}</span>
        <button type="button" className="btn btn-outline btn-small" data-testid="autobed-open" disabled={ro} onClick={() => setOpen(true)}
          title={t("勾几首歌，随机铺进片头、片尾、间隙和间奏之外说话的地方。先给建议，试听后再采用。")}>
          {t("自动铺底")}
        </button>
      </div>
    );
  return (
    <div className="card autobed" data-testid="autobed">
      <div className="row gap8 wrap autobed-head">
        <strong className="grow">{t("自动铺底")}</strong>
        <button type="button" className="btn btn-ghost btn-small" onClick={() => setOpen(false)}>
          {t("收起")}
        </button>
      </div>
      {!v ? (
        <p className="small muted">{t("正在看哪些地方还空着…")}</p>
      ) : (
        <>
          <p className="small muted" data-testid="autobed-meter">
            {v.stretches
              ? t("还空着 {k} 段说话，共 {free}；勾了 {n} 首，共 {total}。", { k: v.stretches, free: fmt(v.free_s), n: chosen.length, total: fmt(total) })
              : t("说话的地方都已经有配乐了（短于 20 秒的空档不铺）。")}
            {v.stretches > 0 && chosen.length > 0 && total < v.free_s && " " + t("歌不够长时会换个顺序再放一轮。")}
          </p>
          {v.songs.length === 0 ? (
            <p className="small muted">{t("素材库里还没有这一集能用的音乐。")}</p>
          ) : (
            <ul className="autobed-list">
              {v.songs.map((s) => (
                <li key={s.id} className={s.used_as ? "is-used" : ""}>
                  <label className="row gap8">
                    <input type="checkbox" checked={!!picked?.has(s.id)} onChange={() => toggle(s.id)} data-testid="autobed-song" />
                    <span className="grow autobed-name">{s.name}</span>
                    <span className="small muted">{s.used_as ? t("已用作{role}", { role: s.used_as }) : s.kind_label}</span>
                    <span className="small muted">{fmt(s.duration_s)}</span>
                  </label>
                </li>
              ))}
            </ul>
          )}
          <div className="row gap8 wrap">
            <span className="small muted grow">{t("两首之间交叉淡化 2 秒；空档结束前 3 秒淡出。")}</span>
            <button type="button" className="btn btn-primary btn-small" data-testid="autobed-fill" disabled={ro || !chosen.length || !v.stretches}
              onClick={() => onRun(autobedApi.fill(id, chosen.map((s) => s.id)))}>
              {done ? t("再随机一次") : t("随机铺满空档")}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
