// 配乐 design B, the left side: the music this episode may use. ▶ hears a piece, 放到 ▾ puts it in by use.
import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { Asset, PlacementPatch, Role } from "./api";
import { fmt } from "../../api";
import { ROLE_NAME } from "./MusicCard";
import { t } from "../../i18n";

const MENU: Role[] = ["intro", "outro", "interlude", "bed"];

export function MusicLibrary({ assets, taken, now, upload, children, onPlace, onPauseOthers }: {
  assets: Asset[];
  /** uses already on the episode (片头 / 片尾 are replaced) */
  taken: Role[];
  /** where the final-mix player is: an interlude goes there */
  now: number;
  upload: ReactNode;
  /** the form for a placement at a written time (below the list) */
  children?: ReactNode;
  onPlace: (body: PlacementPatch & { asset_id: string; role: Role }) => void;
  onPauseOthers: () => void;
}) {
  const [q, setQ] = useState("");
  const [menu, setMenu] = useState<string | null>(null);
  const [playing, setPlaying] = useState<string | null>(null);
  const audio = useRef<HTMLAudioElement>(null);
  useEffect(() => {
    if (!menu) return;
    const close = (e: MouseEvent) => !(e.target as HTMLElement).closest?.(".mlib-menu, .mlib-put") && setMenu(null);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [menu]);
  const hear = (a: Asset) => {
    const el = audio.current;
    if (!el) return;
    if (playing === a.id) {
      el.pause();
      return;
    }
    onPauseOthers();
    el.src = `/api/library/assets/${a.id}/audio`;
    setPlaying(a.id);
    void el.play().catch(() => setPlaying(null));
  };
  const needle = q.trim().toLowerCase();
  const shown = needle ? assets.filter((a) => `${a.name} ${a.credit_line} ${a.kind_label}`.toLowerCase().includes(needle)) : assets;
  const label = (r: Role) => {
    if ((r === "intro" || r === "outro") && taken.includes(r)) return t("{role}（替换现在的）", { role: ROLE_NAME[r] });
    if (r === "interlude") return t("{role}（放在 {at}）", { role: ROLE_NAME[r], at: fmt(now) });
    if (r === "bed") return t("{role}（自动放进空档）", { role: ROLE_NAME[r] });
    return ROLE_NAME[r];
  };
  return (
    <aside className="card mlib" data-testid="music-library" data-tour="music-library">
      <div className="mlib-head">
        <h2>{t("素材库")}</h2>
        <span className="mlib-upload" data-tour="music-upload">{upload}</span>
      </div>
      {assets.length > 3 && (
        <input className="mlib-search" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("搜索素材")} aria-label={t("搜索素材")} />
      )}
      <ul className="mlib-list">
        {shown.map((a) => (
          <li key={a.id} className="mlib-row" data-testid="music-asset" data-tour={`music-asset-${a.kind}`}>
            <button type="button" className="mlib-play" aria-label={playing === a.id ? t("停止试听 {name}", { name: a.name }) : t("试听 {name}", { name: a.name })} onClick={() => hear(a)}>
              {playing === a.id ? "❚❚" : "▶"}
            </button>
            <span className="mlib-name">
              <strong title={a.name}>{a.credit.title || a.name.replace(/\.[^.]+$/, "")}</strong>
              <span className="small muted">
                {fmt(a.duration_s)} · {a.kind_label}
              </span>
            </span>
            <span className="mlib-put-wrap">
              <button type="button" className="btn btn-small btn-outline mlib-put" aria-expanded={menu === a.id} onClick={() => setMenu(menu === a.id ? null : a.id)}>
                {t("放到 ▾")}
              </button>
              {menu === a.id && (
                <span className="mlib-menu" role="menu">
                  {MENU.map((r) => (
                    <button
                      key={r}
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        setMenu(null);
                        onPlace(r === "interlude" ? { asset_id: a.id, role: r, at_s: Math.max(now, 0) } : { asset_id: a.id, role: r });
                      }}
                    >
                      {label(r)}
                    </button>
                  ))}
                </span>
              )}
            </span>
          </li>
        ))}
        {needle && !shown.length && <li className="small muted">{t("没有找到「{q}」", { q: q.trim() })}</li>}
      </ul>
      <p className="small muted mlib-note">{t("请只上传你有权使用的音乐。")}</p>
      <audio ref={audio} onEnded={() => setPlaying(null)} onPause={() => setPlaying(null)} data-testid="asset-audio" />
      {children}
    </aside>
  );
}
