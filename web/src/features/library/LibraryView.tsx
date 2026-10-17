import { useCallback, useEffect, useRef, useState } from "react";
import { GrowText } from "../../components/GrowText";
import type { Asset, Credit, CreditStatus, LibraryView as Lib } from "./api";
import { fmt } from "../../api";
import { libraryApi } from "./api";

export const CREDIT_LABEL: Record<CreditStatus, string> = {
  confirmed: "已确认",
  suggested: "待确认",
  unknown: "还不知道曲名",
};

const FIELDS: { key: keyof Credit; label: string }[] = [
  { key: "title", label: "曲名" },
  { key: "film", label: "电影 / 剧" },
  { key: "composer", label: "作曲" },
  { key: "artist", label: "演唱 / 演奏" },
  { key: "album", label: "原声专辑" },
  { key: "year", label: "年份" },
];

type Upload = { name: string; state: "busy" | "done" | "dup" | "error"; msg?: string };

const ACCEPT = ".mp3,.wav,.flac,.m4a,.aac,.ogg,.opus,.aif,.aiff,.wma,audio/*";

/** Drag files onto the page, or pick them with the system file dialog. The browser sends the
 * bytes to the local app, which keeps them in the library folder. */
function DropZone({ kinds, dragging, onFiles }: { kinds: Record<string, string>; dragging: boolean; onFiles: (files: File[], kind: string) => void }) {
  const [kind, setKind] = useState("other");
  const input = useRef<HTMLInputElement>(null);
  return (
    <div
      className={`card lib-drop${dragging ? " lib-drop-active" : ""}`}
      data-testid="drop-zone"
      data-kind={kind}
    >
      <p className="lib-drop-title">把音乐文件拖到这里</p>
      <div className="row gap12 lib-drop-actions">
        <button type="button" className="btn btn-primary" onClick={() => input.current?.click()}>
          选择文件
        </button>
        <label className="row gap8 small">
          用途
          <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="新文件的用途">
            {Object.entries(kinds).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="small muted">mp3、wav、flac、m4a 等都可以，一次可以拖好几个。</p>
      <input
        ref={input}
        type="file"
        multiple
        accept={ACCEPT}
        hidden
        aria-label="选择音乐文件"
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          e.target.value = "";
          if (files.length) onFiles(files, kind);
        }}
      />
    </div>
  );
}

function AssetRow({ a, kinds, onChange, onRemoved, claude }: { a: Asset; kinds: Record<string, string>; onChange: (a: Asset) => void; onRemoved: () => void; claude: boolean }) {
  const [note, setNote] = useState(a.note);
  const [edit, setEdit] = useState(false);
  const [draft, setDraft] = useState<Partial<Credit>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => setNote(a.note), [a.note]);

  const run = async (label: string, p: Promise<{ asset: Asset; message?: string }>) => {
    setBusy(label);
    setMsg(null);
    try {
      const r = await p;
      onChange(r.asset);
      if (r.message) setMsg(r.message);
      return true;
    } catch (e) {
      setMsg(`失败：${(e as Error).message}`);
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
          aria-label="用途"
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
      <audio controls preload="none" src={`/api/library/assets/${a.id}/audio`} className="lib-audio" />
      <div className="row gap8 align-end">
        <GrowText
          value={note}
          placeholder="随口说一句，比如：这是《奥德赛》的主题曲"
          onChange={setNote}
          onEnter={() => note !== a.note && !busy && void run("save", libraryApi.updateAsset(a.id, { note }))}
          aria-label="备注"
        />
        <button
          type="button"
          className="btn btn-outline"
          disabled={note === a.note || !!busy}
          onClick={() => void run("save", libraryApi.updateAsset(a.id, { note }))}
        >
          保存备注
        </button>
      </div>
      <div className="row gap8 wrap">
        <span data-testid="credit-line">BGM 署名：{a.credit_line}</span>
        <span className={`badge badge-${c.status}`}>{CREDIT_LABEL[c.status]}</span>
        {c.source === "file_tags" && c.status === "suggested" && <span className="muted small">来自文件标签</span>}
        {c.source === "claude" && c.status === "suggested" && <span className="muted small">Claude 查的</span>}
      </div>
      {c.sources?.length > 0 && (
        <p className="small muted">
          出处：
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
          title={!claude ? "没有 API key，Claude 暂时不可用" : !note.trim() ? "先写备注：Claude 听不到音乐，只能按备注去查" : ""}
          onClick={() => {
            const go = note !== a.note ? libraryApi.updateAsset(a.id, { note }).then(() => libraryApi.lookupCredit(a.id)) : libraryApi.lookupCredit(a.id);
            // show what Claude filled in, ready to correct before confirming
            void run("lookup", go.then((r) => (setDraft({ ...r.asset.credit }), setEdit(true), r)));
          }}
        >
          {busy === "lookup" ? "Claude 正在查…" : "让 Claude 查正式曲名"}
        </button>
        {c.status === "suggested" && (
          <button type="button" className="btn btn-outline" disabled={!!busy} onClick={() => void run("confirm", libraryApi.updateAsset(a.id, { confirm: true }))}>
            对，就是这首
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
          {edit ? "收起" : "手动改"}
        </button>
        <span className="grow" />
        <button
          type="button"
          className="btn btn-small btn-outline"
          disabled={!!busy}
          onClick={() => {
            if (window.confirm(`把「${a.name}」移出素材库？文件会放进素材库的 _removed 文件夹，不会删除。`))
              void libraryApi.removeAsset(a.id).then(onRemoved);
          }}
        >
          移出素材库
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
            保存署名
          </button>
        </div>
      )}
    </li>
  );
}

export function LibraryView() {
  const [lib, setLib] = useState<Lib | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [dragging, setDragging] = useState(false);
  const [note, setNote] = useState<string | null>(null);
    const load = useCallback(() => {
    libraryApi
      .library()
      .then(setLib)
      .catch((e) => setErr(String(e.message ?? e)));
  }, []);
  useEffect(load, [load]);

  const addFiles = async (files: File[], kind: string) => {
    setNote(null);
    setUploads(files.map((f) => ({ name: f.name, state: "busy" })));
    for (const [i, f] of files.entries()) {
      let u: Upload;
      try {
        const r = await libraryApi.uploadAsset(f, kind);
        u = r.duplicate
          ? { name: f.name, state: "dup", msg: `素材库里已经有这首（${r.asset.name}）` }
          : { name: f.name, state: "done" };
      } catch (e) {
        u = { name: f.name, state: "error", msg: (e as Error).message };
      }
      setUploads((us) => us.map((x, j) => (j === i ? u : x)));
    }
    load();
  };

  if (err) return <p className="error pad">{err}</p>;
  if (!lib) return <p className="pad muted">加载中…</p>;
  const replace = (a: Asset) => setLib({ ...lib, assets: lib.assets.map((x) => (x.id === a.id ? { ...x, ...a } : x)) });
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
        if (files.length) void addFiles(files, zone?.dataset.kind ?? "other");
      }}
    >
      <div className="row gap8 wrap">
        <h1 className="grow">素材库</h1>
        <button
          type="button"
          className="btn btn-outline"
          onClick={() =>
            void libraryApi.scanLibrary().then((r) => {
              setLib({ ...r, lookup: lib.lookup });
              setNote(r.added.length ? `新加入 ${r.added.length} 个文件` : "文件夹里没有新文件");
            })
          }
        >
          扫描文件夹
        </button>
        <button type="button" className="btn btn-outline" onClick={() => void libraryApi.openLibrary()}>
          打开文件夹
        </button>
      </div>
      <DropZone kinds={lib.kinds} dragging={dragging} onFiles={(f, k) => void addFiles(f, k)} />
      {uploads.length > 0 && (
        <ul className="lib-uploads small" data-testid="uploads">
          {uploads.map((u, i) => (
            <li key={i} className={u.state === "error" ? "error" : ""}>
              {u.state === "busy" ? "正在加入" : u.state === "error" ? "没加进去" : u.state === "dup" ? "跳过" : "已加入"}：{u.name}
              {u.msg && `（${u.msg}）`}
            </li>
          ))}
        </ul>
      )}
      <p className="muted small">
        文件会复制到素材库文件夹 <span className="mono">{lib.folder}</span>，原文件不动。音乐只在这台电脑上，查曲名时只把文件名、标签和你的备注发给 Claude。
      </p>
      {note && <p className="small">{note}</p>}
      {lib.assets.length === 0 && <p className="muted">素材库还是空的。把片头、配乐或台词片段拖进来就行。</p>}
      <ul className="lib-list">
        {lib.assets.map((a) => (
          <AssetRow key={a.id} a={a} kinds={lib.kinds} onChange={replace} onRemoved={load} claude={lib.lookup} />
        ))}
      </ul>
    </main>
  );
}
