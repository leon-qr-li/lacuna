import { useCallback, useEffect, useState } from "react";
import type { Asset, Credit, CreditStatus, LibraryView as Lib } from "../api";
import { api, fmt } from "../api";
import { FileBrowser } from "./ImportPanel";

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

function AddAsset({ kinds, onAdded, onClose }: { kinds: Record<string, string>; onAdded: (a: Asset) => void; onClose: () => void }) {
  const [path, setPath] = useState<string | null>(null);
  const [kind, setKind] = useState("music");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  if (!path) return <FileBrowser label="选择音乐文件" onPick={(p) => setPath(p)} onClose={onClose} />;
  const add = async () => {
    setBusy(true);
    setErr(null);
    try {
      onAdded((await api.addAsset(path, kind, note)).asset);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="card lib-add" role="dialog" aria-label="加入素材库">
      <p className="mono small">{path}</p>
      <div className="row gap8 wrap">
        <label className="row gap8">
          用途
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            {Object.entries(kinds).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <input
          className="grow"
          placeholder="随口说一句，比如：这是《奥德赛》的主题曲"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          aria-label="备注"
        />
      </div>
      {err && <p className="error small">{err}</p>}
      <div className="row gap8">
        <button type="button" className="btn btn-primary" disabled={busy} onClick={() => void add()}>
          {busy ? "正在分析…" : "加入素材库"}
        </button>
        <button type="button" className="btn btn-outline" onClick={onClose}>
          取消
        </button>
      </div>
    </div>
  );
}

function AssetRow({ a, onChange, onRemoved, claude }: { a: Asset; onChange: (a: Asset) => void; onRemoved: () => void; claude: boolean }) {
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
        <span className="chip">{a.kind_label}</span>
        <span className="muted small mono">
          {fmt(a.duration_s)}
          {a.lufs != null && ` · ${a.lufs.toFixed(1)} LUFS`}
        </span>
      </div>
      <audio controls preload="none" src={`/api/library/assets/${a.id}/audio`} className="lib-audio" />
      <div className="row gap8">
        <input
          className="grow"
          value={note}
          placeholder="随口说一句，比如：这是《奥德赛》的主题曲"
          onChange={(e) => setNote(e.target.value)}
          aria-label="备注"
        />
        <button
          type="button"
          className="btn btn-outline"
          disabled={note === a.note || !!busy}
          onClick={() => void run("save", api.updateAsset(a.id, { note }))}
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
          disabled={!!busy || !claude}
          title={claude ? "" : "没有 API key，Claude 暂时不可用"}
          onClick={() => {
            const go = note !== a.note ? api.updateAsset(a.id, { note }).then(() => api.lookupCredit(a.id)) : api.lookupCredit(a.id);
            void run("lookup", go);
          }}
        >
          {busy === "lookup" ? "Claude 正在查…" : "让 Claude 查正式曲名"}
        </button>
        {c.status === "suggested" && (
          <button type="button" className="btn btn-outline" disabled={!!busy} onClick={() => void run("confirm", api.updateAsset(a.id, { confirm: true }))}>
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
              void api.removeAsset(a.id).then(onRemoved);
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
                api.updateAsset(a.id, {
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
  const [adding, setAdding] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const load = useCallback(() => {
    api
      .library()
      .then(setLib)
      .catch((e) => setErr(String(e.message ?? e)));
  }, []);
  useEffect(load, [load]);
  if (err) return <p className="error pad">{err}</p>;
  if (!lib) return <p className="pad muted">加载中…</p>;
  const replace = (a: Asset) => setLib({ ...lib, assets: lib.assets.map((x) => (x.id === a.id ? { ...x, ...a } : x)) });
  return (
    <main className="home library">
      <div className="row gap8 wrap">
        <h1 className="grow">素材库</h1>
        <button type="button" className="btn btn-primary" onClick={() => setAdding(true)}>
          添加音乐文件
        </button>
        <button
          type="button"
          className="btn btn-outline"
          onClick={() =>
            void api.scanLibrary().then((r) => {
              setLib({ ...r, lookup: lib.lookup });
              setNote(r.added.length ? `新加入 ${r.added.length} 个文件` : "文件夹里没有新文件");
            })
          }
        >
          扫描文件夹
        </button>
        <button type="button" className="btn btn-outline" onClick={() => void api.openLibrary()}>
          打开文件夹
        </button>
      </div>
      <p className="muted small">
        文件夹：<span className="mono">{lib.folder}</span>。也可以直接把文件丢进里面的 music / jingles / clips，再点「扫描文件夹」。音乐只在这台电脑上，查曲名时只把文件名、标签和你的备注发给 Claude。
      </p>
      {note && <p className="small">{note}</p>}
      {adding && (
        <AddAsset
          kinds={lib.kinds}
          onClose={() => setAdding(false)}
          onAdded={(a) => {
            setAdding(false);
            load();
            setNote(`已加入：${a.name}`);
          }}
        />
      )}
      {lib.assets.length === 0 && <p className="muted">素材库还是空的。点「添加音乐文件」，选片头、配乐或台词片段。</p>}
      <ul className="lib-list">
        {lib.assets.map((a) => (
          <AssetRow key={a.id} a={a} onChange={replace} onRemoved={load} claude={lib.lookup} />
        ))}
      </ul>
    </main>
  );
}
