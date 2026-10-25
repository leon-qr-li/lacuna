import { useCallback, useEffect, useRef, useState } from "react";
import { GrowText } from "../../components/GrowText";
import type { AlbumRef, Asset, Credit, CreditStatus, EpisodeRef, LibraryView as Lib } from "./api";
import { fmt } from "../../api";
import { libraryApi } from "./api";
import { t } from "../../i18n";
import { BusyLabel, PageLoading } from "../loading/Loading";
import { confirmDialog } from "../dialog/Dialog";
import { inScope, ScopeActions, ScopeBadge, ScopeFilter, ScopeTarget } from "./Scope";
import { useCloud } from "../auth/cloud";

export const CREDIT_LABEL: Record<CreditStatus, string> = {
  confirmed: t("已确认"),
  suggested: t("待确认"),
  unknown: t("还不知道曲名"),
};

const FIELDS: { key: keyof Credit; label: string }[] = [
  { key: "title", label: t("曲名") },
  { key: "film", label: t("电影 / 剧") },
  { key: "composer", label: t("作曲") },
  { key: "artist", label: t("演唱 / 演奏") },
  { key: "album", label: t("原声专辑") },
  { key: "year", label: t("年份") },
];

type Upload = { name: string; state: "busy" | "done" | "dup" | "error"; msg?: string };

const ACCEPT = ".mp3,.wav,.flac,.m4a,.aac,.ogg,.opus,.aif,.aiff,.wma,audio/*";

/** Drag files onto the page, or pick them with the system file dialog. The browser sends the
 * bytes to the local app, which keeps them in the library folder. */
function DropZone({ kinds, eps, albums, dragging, onFiles }: {
  kinds: Record<string, string>;
  eps: EpisodeRef[];
  albums: AlbumRef[];
  dragging: boolean;
  onFiles: (files: File[], kind: string, episode: string) => void;
}) {
  const [kind, setKind] = useState("other");
  const [target, setTarget] = useState(""); // "" = the whole project, "al:<id>" an album, else one episode
  const input = useRef<HTMLInputElement>(null);
  return (
    <div
      className={`card lib-drop${dragging ? " lib-drop-active" : ""}`}
      data-testid="drop-zone"
      data-kind={kind}
      data-episode={target}
    >
      <p className="lib-drop-title">{t("把音乐文件拖到这里")}</p>
      <div className="row gap12 lib-drop-actions">
        <button type="button" className="btn btn-primary" onClick={() => input.current?.click()}>
          {t("选择文件")}
        </button>
        <label className="row gap8 small">
          {t("用途")}
          <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label={t("新文件的用途")}>
            {Object.entries(kinds).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <ScopeTarget eps={eps} albums={albums} value={target} onChange={setTarget} />
      </div>
      <p className="small muted">{t("mp3、wav、flac、m4a 等都可以，一次可以拖好几个。")}</p>
      <input
        ref={input}
        type="file"
        multiple
        accept={ACCEPT}
        hidden
        aria-label={t("选择音乐文件")}
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          e.target.value = "";
          if (files.length) onFiles(files, kind, target);
        }}
      />
    </div>
  );
}

function AssetRow({ a, kinds, eps, albums, onChange, onRemoved, claude }: { a: Asset; kinds: Record<string, string>; eps: EpisodeRef[]; albums: AlbumRef[]; onChange: (a: Asset) => void; onRemoved: () => void; claude: boolean }) {
  const [note, setNote] = useState(a.note);
  const [edit, setEdit] = useState(false);
  const [draft, setDraft] = useState<Partial<Credit>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => setNote(a.note), [a.note]);

  const run = async (label: string, p: Promise<{ asset: Asset; message?: string | null }>) => {
    setBusy(label);
    setMsg(null);
    try {
      const r = await p;
      onChange(r.asset);
      if (r.message) setMsg(r.message);
      return true;
    } catch (e) {
      setMsg(t("失败：{message}", { message: (e as Error).message }));
      return false;
    } finally {
      setBusy(null);
    }
  };
  const c = a.credit;
  return (
    <li className="card lib-row" data-testid="asset-row">
      <div className="row gap12 wrap">
        <strong className="grow">{a.name}</strong>
        <select
          className="chip-select"
          value={a.kind}
          aria-label={t("用途")}
          disabled={!!busy}
          onChange={(e) => void run("kind", libraryApi.updateAsset(a.id, { kind: e.target.value }))}
        >
          {Object.entries(kinds).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
        <span className="muted small mono">
          {fmt(a.duration_s)}
          {a.lufs != null && ` · ${a.lufs.toFixed(1)} LUFS`}
        </span>
      </div>
      <div className="row gap8 wrap">
        <ScopeBadge a={a} eps={eps} albums={albums} />
        <ScopeActions a={a} eps={eps} albums={albums} disabled={!!busy} onChange={(p) => void run("scope", p)} />
      </div>
      <audio controls preload="none" src={`/api/library/assets/${a.id}/audio`} className="lib-audio" />
      <div className="row gap8 align-end">
        <GrowText
          value={note}
          placeholder={t("随口说一句，比如：这是《奥德赛》的主题曲")}
          onChange={setNote}
          onEnter={() => note !== a.note && !busy && void run("save", libraryApi.updateAsset(a.id, { note }))}
          aria-label={t("备注")}
        />
        <button
          type="button"
          className="btn btn-outline"
          disabled={note === a.note || !!busy}
          onClick={() => void run("save", libraryApi.updateAsset(a.id, { note }))}
        >
          {t("保存备注")}
        </button>
      </div>
      <div className="row gap8 wrap">
        <span data-testid="credit-line">{t("BGM 署名：")}{a.credit_line}</span>
        <span className={`badge badge-${c.status}`}>{CREDIT_LABEL[c.status]}</span>
        {c.source === "file_tags" && c.status === "suggested" && <span className="muted small">{t("来自文件标签")}</span>}
        {c.source === "claude" && c.status === "suggested" && <span className="muted small">{t("LACUNA 查的")}</span>}
      </div>
      {c.sources?.length > 0 && (
        <p className="small muted">
          {t("出处：")}
          {c.sources.slice(0, 3).map((u) => (
            <a key={u} href={u} target="_blank" rel="noreferrer" className="lib-src">
              {new URL(u).hostname}
            </a>
          ))}
        </p>
      )}
      {msg && <p className="small">{msg}</p>}
      <div className="row gap8 wrap">
        <button
          type="button"
          className="btn btn-primary"
          disabled={!!busy || !claude || !note.trim()}
          title={!claude ? t("没有 AI 密钥，暂时查不了") : !note.trim() ? t("先写备注：LACUNA 听不到音乐，只能按备注去查") : ""}
          onClick={() => {
            const go = note !== a.note ? libraryApi.updateAsset(a.id, { note }).then(() => libraryApi.lookupCredit(a.id)) : libraryApi.lookupCredit(a.id);
            // show what Claude filled in, ready to correct before confirming
            void run("lookup", go.then((r) => (setDraft({ ...r.asset.credit }), setEdit(true), r)));
          }}
        >
          <BusyLabel busy={busy === "lookup"} label={t("让 LACUNA 查正式曲名")} busyLabel={t("LACUNA 正在查…")} />
        </button>
        {c.status === "suggested" && (
          <button type="button" className="btn btn-outline" disabled={!!busy} onClick={() => void run("confirm", libraryApi.updateAsset(a.id, { confirm: true }))}>
            {t("对，就是这首")}
          </button>
        )}
        <button
          type="button"
          className="btn btn-outline"
          onClick={() => {
            setDraft({ ...c });
            setEdit(!edit);
          }}
        >
          {edit ? t("收起") : t("手动改")}
        </button>
        <span className="grow" />
        <button
          type="button"
          className="btn btn-small btn-outline"
          disabled={!!busy}
          onClick={async () => {
            const ok = await confirmDialog({
              title: t("移出素材库"),
              message: t("把「{name}」移出素材库？移出后素材库里就看不到它了。", { name: a.name }),
              confirmLabel: t("移出"),
              danger: true,
            });
            if (ok) void libraryApi.removeAsset(a.id).then(onRemoved);
          }}
        >
          {t("移出素材库")}
        </button>
      </div>
      {edit && (
        <div className="lib-edit">
          {FIELDS.map((f) => (
            <label key={f.key} className="row gap8">
              <span className="lib-label">{f.label}</span>
              <input
                className="grow"
                value={(draft[f.key] as string | number | null | undefined) ?? ""}
                onChange={(e) => setDraft({ ...draft, [f.key]: e.target.value })}
              />
            </label>
          ))}
          <button
            type="button"
            className="btn btn-primary"
            disabled={!!busy}
            onClick={() =>
              void run(
                "credit",
                libraryApi.updateAsset(a.id, {
                  credit: Object.fromEntries(FIELDS.map((f) => [f.key, draft[f.key] ?? null])) as Partial<Credit>,
                }),
              ).then((ok) => ok && setEdit(false))
            }
          >
            {t("保存署名")}
          </button>
        </div>
      )}
    </li>
  );
}

export function LibraryView() {
  const cloud = useCloud();
  const [lib, setLib] = useState<Lib | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [dragging, setDragging] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const load = useCallback(() => {
    libraryApi
      .library()
      .then(setLib)
      .catch((e) => setErr(String(e.message ?? e)));
  }, []);
  useEffect(load, [load]);

  /** `target`: "" the whole project, "al:<id>" an album, else one episode */
  const addFiles = async (files: File[], kind: string, target = "") => {
    const album = target.startsWith("al:") ? target.slice(3) : "";
    const episode = album ? "" : target;
    setNote(null);
    setUploads(files.map((f) => ({ name: f.name, state: "busy" })));
    for (const [i, f] of files.entries()) {
      let u: Upload;
      try {
        const r = await libraryApi.uploadAsset(f, kind, "", episode, album);
        u = r.duplicate
          ? { name: f.name, state: "dup", msg: t("素材库里已经有这首（{name}）", { name: r.asset.name }) }
          : { name: f.name, state: "done" };
      } catch (e) {
        u = { name: f.name, state: "error", msg: (e as Error).message };
      }
      setUploads((us) => us.map((x, j) => (j === i ? u : x)));
    }
    load();
  };

  if (err) return <p className="error pad">{err}</p>;
  if (!lib) return <PageLoading label={t("正在打开素材库…")} shape="list" />;
  // functional update: lookups finish at different times, and each result lands on the latest list
  // (a result applied to the list as it was when its button was clicked wiped out the others, item 14)
  const replace = (a: Asset) => setLib((l) => l && { ...l, assets: l.assets.map((x) => (x.id === a.id ? { ...x, ...a } : x)) });
  const hasFiles = (e: React.DragEvent) => Array.from(e.dataTransfer.types).includes("Files");
  return (
    <main
      className="home library"
      onDragOver={(e) => {
        if (!hasFiles(e)) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "copy";
        setDragging(true);
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false);
      }}
      onDrop={(e) => {
        if (!hasFiles(e)) return;
        e.preventDefault();
        setDragging(false);
        const zone = (e.currentTarget as HTMLElement).querySelector<HTMLElement>("[data-testid=drop-zone]");
        const files = Array.from(e.dataTransfer.files);
        if (files.length) void addFiles(files, zone?.dataset.kind ?? "other", zone?.dataset.episode ?? "");
      }}
    >
      <div className="row gap8 wrap">
        <h1 className="grow">{t("素材库")}</h1>
        {cloud === false && (
          <>
            <button
              type="button"
              className="btn btn-outline"
              onClick={() =>
                void libraryApi.scanLibrary().then((r) => {
                  setLib((l) => ({ ...r, lookup: l?.lookup ?? lib.lookup, episodes: l?.episodes ?? lib.episodes }));
                  setNote(r.added.length ? t("新加入 {length} 个文件", { length: r.added.length }) : t("文件夹里没有新文件"));
                })
              }
            >
              {t("扫描文件夹")}
            </button>
            <button type="button" className="btn btn-outline" onClick={() => void libraryApi.openLibrary()}>
              {t("打开文件夹")}
            </button>
          </>
        )}
      </div>
      <DropZone kinds={lib.kinds} eps={lib.episodes} albums={lib.albums} dragging={dragging} onFiles={(f, k, e) => void addFiles(f, k, e)} />
      {uploads.length > 0 && (
        <ul className="lib-uploads small" data-testid="uploads">
          {uploads.map((u, i) => (
            <li key={i} className={u.state === "error" ? "error" : ""}>
              {u.state === "busy"
                ? <BusyLabel busy label={t("正在加入：{name}", u)} />
                : u.state === "error"
                  ? t("没加进去：{name}", u)
                  : u.state === "dup"
                    ? t("跳过：{name}", u)
                    : t("已加入：{name}", u)}
              {u.msg && `（${u.msg}）`}
            </li>
          ))}
        </ul>
      )}
      {cloud === false && (
        <p className="muted small">
          {t("文件会复制到素材库文件夹")} <span className="mono">{lib.folder}</span>{t("，原文件不动。音乐只在这台电脑上，查曲名时只把文件名、标签和你的备注发给 LACUNA。")}
        </p>
      )}
      {cloud && <p className="muted small">{t("音乐保存在 LACUNA 的服务器上，原文件不动。查曲名时只把文件名、标签和你的备注发给 LACUNA 的 AI。")}</p>}
      {note && <p className="small">{note}</p>}
      {lib.assets.length === 0 && <p className="muted">{t("素材库还是空的。把片头、配乐或台词片段拖进来就行。")}</p>}
      {lib.assets.length > 0 && <ScopeFilter eps={lib.episodes} albums={lib.albums} value={filter} onChange={setFilter} />}
      {lib.assets.length > 0 && !lib.assets.some((a) => inScope(a, filter)) && <p className="muted">{t("这里还没有素材。")}</p>}
      <ul className="lib-list">
        {lib.assets
          .filter((a) => inScope(a, filter))
          .map((a) => (
            <AssetRow key={a.id} a={a} kinds={lib.kinds} eps={lib.episodes} albums={lib.albums} onChange={replace} onRemoved={load} claude={lib.lookup} />
          ))}
      </ul>
    </main>
  );
}
