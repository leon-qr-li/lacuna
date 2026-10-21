import { useEffect, useRef, useState } from "react";
import type { EpisodeListItem } from "../../api";
import { t } from "../../i18n";
import { confirmDialog } from "../dialog/Dialog";
import { libraryApi, type Asset } from "../library/api";
import { BusyLabel } from "../loading/Loading";
import { AlbumCover } from "./Cover";
import { albumsApi, type Album, type AlbumsView } from "./api";

/** 新建专辑 / 专辑设置 (one form): name, cover, about, default opener and ending (empty: the project's)
 *  and, when creating, episodes to put in. Esc or the backdrop cancels. */
export function AlbumDialog({ album, view, loose, preset, onClose, onSaved }: {
  /** the album being edited; none: a new one */
  album?: Album;
  view: AlbumsView;
  /** episodes in no album, offered when creating */
  loose?: EpisodeListItem[];
  /** episodes to put in the new album (「＋ 新专辑…」 on an episode's card) */
  preset?: string[];
  onClose: () => void;
  /** after a save (`created`: the new album's id) or a delete (`deleted`) */
  onSaved: (v: AlbumsView, r: { created?: string; deleted?: boolean }) => void;
}) {
  const [name, setName] = useState(album?.name ?? "");
  const [about, setAbout] = useState(album?.about ?? "");
  const [intro, setIntro] = useState(album?.intro?.asset_id ?? "");
  const [outro, setOutro] = useState(album?.outro?.asset_id ?? "");
  const [picked, setPicked] = useState<string[]>(preset ?? []);
  const [cover, setCover] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(album?.cover_url ?? null);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const asking = useRef(false); // the delete question is open: its Esc is its own

  useEffect(() => {
    nameRef.current?.focus();
    libraryApi
      .library()
      .then((lib) => setAssets(lib.assets))
      .catch(() => setAssets([]));
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !asking.current) {
        e.stopPropagation();
        onClose();
      }
    };
    window.addEventListener("keydown", key, true);
    return () => window.removeEventListener("keydown", key, true);
  }, [onClose]);
  useEffect(() => {
    if (!cover) return;
    const url = URL.createObjectURL(cover);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [cover]);

  const fromProject = (role: "intro" | "outro") => view.project[role]?.name;
  // what each slot offers: the uses that fit first (an opener for the opener), then the rest
  const options = (kind: "intro" | "outro") => [...assets].sort((a, b) => Number(b.kind === kind) - Number(a.kind === kind));

  const save = async () => {
    setBusy(true);
    setErr(null);
    try {
      let v: AlbumsView;
      let created: string | undefined;
      if (album) {
        v = await albumsApi.update(album.id, { name, about, intro, outro });
      } else {
        const r = await albumsApi.create({ name, about, intro, outro, episodes: [...new Set([...(preset ?? []), ...picked])] });
        v = r;
        created = r.created;
      }
      const id = album?.id ?? created!;
      if (cover) v = await albumsApi.cover(id, cover);
      onSaved(v, { created });
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const remove = async () => {
    if (!album) return;
    asking.current = true;
    const ok = await confirmDialog({
      title: t("删除专辑「{name}」？", { name: album.name }),
      message: t("里面的剧集不会删，会变成「不在专辑里」；只给这个专辑用的素材会变成整个节目都能用。"),
      confirmLabel: t("删除专辑"),
      danger: true,
    });
    asking.current = false;
    if (!ok) return;
    setBusy(true);
    try {
      onSaved(await albumsApi.remove(album.id), { deleted: true });
    } catch (e) {
      setErr((e as Error).message);
      setBusy(false);
    }
  };

  const shown = { id: album?.id ?? "new", name: name || "?", cover_url: preview };
  return (
    <div className="dlg-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <form
        className="dlg alb-dlg"
        role="dialog"
        aria-modal="true"
        aria-labelledby="alb-dlg-title"
        data-testid="album-dialog"
        onSubmit={(e) => {
          e.preventDefault();
          if (name.trim() && !busy) void save();
        }}
      >
        <h2 id="alb-dlg-title">{album ? t("专辑设置") : t("新建专辑")}</h2>
        <div className="alb-dlg-head">
          <AlbumCover a={shown} size={76} />
          <div className="alb-dlg-fields">
            <label className="alb-field">
              <span className="alb-label">{t("专辑名")}</span>
              <input ref={nameRef} value={name} maxLength={80} onChange={(e) => setName(e.target.value)} placeholder={t("比如：九十年代港片")} data-testid="album-name" />
            </label>
            <div className="row gap8">
              <button type="button" className="btn btn-small btn-outline" onClick={() => fileRef.current?.click()}>
                {preview ? t("换封面") : t("上传封面")}
              </button>
              <span className="small muted">{t("不传就用一张渐变色封面")}</span>
              <input
                ref={fileRef}
                type="file"
                accept="image/png,image/jpeg,image/webp"
                hidden
                aria-label={t("选择封面图片")}
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  e.target.value = "";
                  if (f) setCover(f);
                }}
              />
            </div>
          </div>
        </div>
        <label className="alb-field">
          <span className="alb-label">{t("简介（可不填）")}</span>
          <input value={about} maxLength={400} onChange={(e) => setAbout(e.target.value)} />
        </label>
        <div className="alb-two">
          {(["intro", "outro"] as const).map((role) => (
            <label className="alb-field" key={role}>
              <span className="alb-label">{role === "intro" ? t("默认片头") : t("默认片尾")}</span>
              <select
                value={role === "intro" ? intro : outro}
                onChange={(e) => (role === "intro" ? setIntro : setOutro)(e.target.value)}
                data-testid={`album-${role}`}
              >
                <option value="">
                  {fromProject(role) ? t("沿用节目：{name}", { name: fromProject(role)! }) : t("沿用节目（节目也没有设）")}
                </option>
                {options(role).map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>
        <p className="small muted alb-hint">{t("专辑设了片头片尾，就用专辑的，不用节目的；以后放进这个专辑的新剧集会自动带上。")}</p>
        {!album && !!loose?.length && (
          <fieldset className="alb-field alb-pick">
            <legend className="alb-label">{t("把这些剧集放进来（可不选）")}</legend>
            {loose.map((e) => (
              <label key={e.id} className="alb-pick-row">
                <input
                  type="checkbox"
                  checked={picked.includes(e.id)}
                  onChange={(x) => setPicked((p) => (x.target.checked ? [...p, e.id] : p.filter((i) => i !== e.id)))}
                />
                <span className="mono small">{e.id}</span> {e.title}
              </label>
            ))}
          </fieldset>
        )}
        {err && <p className="error small">{err}</p>}
        <div className="dlg-actions">
          {album && (
            <button type="button" className="btn btn-ghost alb-delete" disabled={busy} onClick={() => void remove()}>
              {t("删除专辑")}
            </button>
          )}
          <span className="grow" />
          <button type="button" className="btn btn-outline" onClick={onClose}>
            {t("取消")}
          </button>
          <button type="submit" className="btn btn-primary" disabled={!name.trim() || busy} data-testid="album-save">
            <BusyLabel busy={busy} label={album ? t("保存") : t("建好专辑")} />
          </button>
        </div>
      </form>
    </div>
  );
}
