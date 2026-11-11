import { t } from "../../i18n";
import { AlbumCover } from "./Cover";
import { albumHref, type AlbumsView } from "./api";

/** 项目首页: the albums as a row of covers (each opens its album page), and 「＋ 新专辑」. */
export function AlbumRow({ view, onNew }: { view: AlbumsView; onNew?: () => void }) {
  return (
    <ul className="alb-row" aria-label={t("专辑")} data-testid="album-row">
      {view.albums.map((a) => {
        const intro = a.intro ?? view.project.intro;
        return (
          <li key={a.id}>
            <a className="alb-tile" href={albumHref(a.id)} data-testid="album-tile">
              <AlbumCover a={a} />
              <span className="alb-tile-body">
                <strong>{a.name}</strong>
                <span className="muted small">{t("{n} 集", { n: a.episodes.length })}</span>
                {intro?.name && <span className="alb-music small">{intro.name}</span>}
              </span>
            </a>
          </li>
        );
      })}
      {onNew && (
        <li>
          <button type="button" className="alb-tile alb-tile-new" onClick={onNew} data-testid="album-new">
            {t("＋ 新专辑")}
          </button>
        </li>
      )}
    </ul>
  );
}
