import { useEffect, useRef, useState } from "react";
import { t } from "../../i18n";
import { albumsApi, type AlbumsView } from "./api";

/** On an episode card: 「移到专辑」, a small menu of the albums, 不在专辑里 and ＋ 新专辑…. */
export function MoveToAlbum({ episode, title, view, onMoved, onNew }: {
  episode: string;
  title: string;
  view: AlbumsView;
  onMoved: (v: AlbumsView) => void;
  /** 「＋ 新专辑…」: make one with this episode in it */
  onNew: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const current = view.episodes[episode] ?? null;

  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    const key = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", key);
    };
  }, [open]);

  const move = (album: string | null) => {
    setOpen(false);
    if (album === current) return;
    albumsApi
      .setEpisode(episode, album)
      .then(onMoved)
      .catch((e) => setErr((e as Error).message));
  };
  const item = (label: string, album: string | null) => (
    <button
      type="button"
      role="menuitemradio"
      aria-checked={album === current}
      className="alb-menu-item"
      onClick={() => move(album)}
      key={album ?? "none"}
    >
      <span className="alb-menu-check" aria-hidden="true">
        {album === current ? "✓" : ""}
      </span>
      {label}
    </button>
  );
  return (
    <div className="alb-move" ref={box}>
      <button
        type="button"
        className="btn btn-ghost btn-small"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={t("把「{title}」移到专辑", { title })}
        onClick={() => setOpen((o) => !o)}
        data-testid="album-move"
      >
        {t("移到专辑")}
      </button>
      {open && (
        <div className="alb-menu" role="menu" data-testid="album-menu">
          {view.albums.map((a) => item(a.name, a.id))}
          {item(t("不在专辑里"), null)}
          <hr />
          <button
            type="button"
            role="menuitem"
            className="alb-menu-item"
            onClick={() => {
              setOpen(false);
              onNew();
            }}
          >
            <span className="alb-menu-check" aria-hidden="true" />
            {t("＋ 新专辑…")}
          </button>
        </div>
      )}
      {err && (
        <span className="error small" role="alert">
          {err}
        </span>
      )}
    </div>
  );
}
