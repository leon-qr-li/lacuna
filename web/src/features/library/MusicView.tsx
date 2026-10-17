import { useCallback, useEffect, useRef, useState } from "react";
import type { Asset, Kind, MusicView as Music, Placement, PlacementPatch, Role } from "./api";
import { fmt, parseTime } from "../../api";
import { CREDIT_LABEL } from "./LibraryView";
import { libraryApi } from "./api";
import { DraftCard, MusicChatBox } from "./MusicAssist";

const ROLE_HELP: Record<Role, string> = {
  intro: "从头放，人声在音乐结束前进来，重叠处音乐自动压低淡出",
  interlude: "在两句话之间插入，正常音量；前后重叠处压在人声下",
  outro: "人声快结束时进来，人声说完后正常音量",
  bed: "垫在说话下面，很低，有人说话时再压低",
  clip: "插入一段台词，前后各留一点空",
};
const ANCHORED: Role[] = ["interlude", "bed", "clip"];

function Num({ label, value, onChange, step = 0.5, min = 0 }: { label: string; value: number; onChange: (v: number) => void; step?: number; min?: number }) {
  return (
    <label className="row gap8 small">
      {label}
      <input type="number" className="num" step={step} min={min} value={value} onChange={(e) => onChange(Number(e.target.value))} />
    </label>
  );
}

function PlacementRow({ p, onSave, onRemove, onPreview, previewing }: {
  p: Placement;
  onSave: (patch: PlacementPatch) => Promise<boolean>;
  onRemove: () => void;
  onPreview: () => void;
  previewing: boolean;
}) {
  const [d, setD] = useState({ src_in_s: p.src_in_s, src_out_s: p.src_out_s, overlap_s: p.overlap_s, gain_db: p.gain_db });
  useEffect(
    () => setD({ src_in_s: p.src_in_s, src_out_s: p.src_out_s, overlap_s: p.overlap_s, gain_db: p.gain_db }),
    [p.src_in_s, p.src_out_s, p.overlap_s, p.gain_db],
  );
  const dirty = d.src_in_s !== p.src_in_s || d.src_out_s !== p.src_out_s || d.overlap_s !== p.overlap_s || d.gain_db !== p.gain_db;
  const save = () => void onSave({ ...d });
  const [pos, setPos] = useState(p.at_s != null ? fmt(p.at_s) : "");
  useEffect(() => setPos(p.at_s != null ? fmt(p.at_s) : ""), [p.at_s]);
  const moveTo = (t: number | null) => t != null && void onSave({ at_s: Math.max(0, Math.round(t * 1000) / 1000) });
  return (
    <li className="card music-row" data-testid="placement">
      <div className="row gap12 wrap">
        <span className={`chip role-chip role-${p.role}`}>{p.role_label}</span>
        <strong className="grow">{p.missing ? "素材已不在库里" : p.asset_name}</strong>
        {p.start_s != null && (
          <span className="mono small">
            {fmt(p.start_s)} – {fmt(p.end_s ?? 0)}
            {p.inserted_s ? ` · 插入 ${p.inserted_s.toFixed(1)} 秒` : ""}
          </span>
        )}
      </div>
      <div className="row gap8 wrap small">
        <span>BGM 署名：{p.credit_line}</span>
        {p.credit_status && <span className={`badge badge-${p.credit_status}`}>{CREDIT_LABEL[p.credit_status]}</span>}
      </div>
      {!p.missing && (
        <div className="row gap12 wrap music-tune">
          <Num label="从（秒）" value={d.src_in_s} onChange={(v) => setD({ ...d, src_in_s: v })} />
          <Num label="到（秒）" value={d.src_out_s} onChange={(v) => setD({ ...d, src_out_s: v })} />
          {p.role !== "bed" && p.role !== "clip" && <Num label="和人声重叠（秒）" value={d.overlap_s} onChange={(v) => setD({ ...d, overlap_s: v })} />}
          <Num label="音量（dB）" value={d.gain_db} step={1} min={-30} onChange={(v) => setD({ ...d, gain_db: v })} />
          <button type="button" className="btn btn-small" disabled={!dirty} onClick={save}>
            保存
          </button>
        </div>
      )}
      <div className="row gap8 wrap">
        {ANCHORED.includes(p.role) && p.at_s != null && (
          <span className="row gap4 wrap small" data-testid="placement-position">
            位置
            <input
              className="time"
              value={pos}
              onChange={(e) => setPos(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && moveTo(parseTime(pos))}
              onBlur={() => parseTime(pos) !== null && parseTime(pos) !== Math.floor(p.at_s!) && moveTo(parseTime(pos))}
              aria-label="位置（成品时间）"
            />
            <button type="button" className="btn btn-small btn-outline" onClick={() => moveTo(p.at_s! - 1)}>
              早 1 秒
            </button>
            <button type="button" className="btn btn-small btn-outline" onClick={() => moveTo(p.at_s! + 1)}>
              晚 1 秒
            </button>
          </span>
        )}
        <span className="grow" />
        {!p.missing && p.start_s != null && (
          <button type="button" className="btn btn-small btn-outline" onClick={onPreview} aria-pressed={previewing}>
            {previewing ? "停止" : "试听这一处"}
          </button>
        )}
        <button type="button" className="btn btn-small btn-outline" onClick={onRemove}>
          去掉
        </button>
      </div>
    </li>
  );
}

function AddPlacement({ assets, kindRoles, onAdd }: {
  assets: Asset[];
  kindRoles: Partial<Record<Kind, Role>>;
  onAdd: (body: PlacementPatch & { asset_id: string; role: Role }) => Promise<boolean>;
}) {
  const roleOf = (aid: string): Role => kindRoles[assets.find((a) => a.id === aid)?.kind ?? "other"] ?? "interlude";
  const [assetId, setAssetId] = useState(assets[0]?.id ?? "");
  const [role, setRole] = useState<Role>(() => roleOf(assets[0]?.id ?? ""));
  const [at, setAt] = useState("");
  const [until, setUntil] = useState("");
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (!assets.find((a) => a.id === assetId)) {
      setAssetId(assets[0]?.id ?? "");
      setRole(roleOf(assets[0]?.id ?? ""));
    }
  }, [assets, assetId]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!assets.length)
    return (
      <p className="muted">
        素材库里还没有音乐。先去 <a href="#/library">素材库</a> 添加片头、配乐或台词。
      </p>
    );
  const add = () => {
    const body: PlacementPatch & { asset_id: string; role: Role } = { asset_id: assetId, role };
    if (ANCHORED.includes(role)) {
      const t = parseTime(at);
      if (t == null) {
        setErr("请写位置，比如 45:59（成品时间）");
        return;
      }
      body.at_s = t;
      const u = role === "bed" ? parseTime(until) : null;
      if (u != null) body.until_s = u;
    }
    setErr(null);
    void onAdd(body).then((ok) => ok && setAt(""));
  };
  return (
    <div className="card music-add">
      <h2>放一段音乐</h2>
      <div className="row gap8 wrap">
        <select
          value={assetId}
          onChange={(e) => {
            setAssetId(e.target.value); // the asset's use in the library decides where it goes
            setRole(roleOf(e.target.value));
          }}
          aria-label="选择素材"
        >
          {assets.map((a) => (
            <option key={a.id} value={a.id}>
              {a.credit_line !== a.name.replace(/\.[^.]+$/, "") ? `${a.credit_line}（${a.name}）` : a.name} · {a.kind_label}
            </option>
          ))}
        </select>
        <select value={role} onChange={(e) => setRole(e.target.value as Role)} aria-label="用途">
          <option value="intro">片头</option>
          <option value="interlude">间奏 / 休息间隙</option>
          <option value="outro">片尾</option>
          <option value="bed">铺底</option>
          <option value="clip">台词</option>
        </select>
        {ANCHORED.includes(role) && (
          <input className="time" value={at} onChange={(e) => setAt(e.target.value)} placeholder="位置 45:59" aria-label="位置" />
        )}
        {role === "bed" && (
          <input className="time" value={until} onChange={(e) => setUntil(e.target.value)} placeholder="到 47:00（可空）" aria-label="铺到" />
        )}
        <button type="button" className="btn btn-primary" onClick={add}>
          放进去
        </button>
      </div>
      <p className="small muted">{ROLE_HELP[role]}</p>
      {err && <p className="error small">{err}</p>}
    </div>
  );
}

/** The whole final episode at a glance: the voice, and each piece of music where it sits. Click a block to hear it. */
function MusicStrip({ m, previewing, onPreview }: { m: Music; previewing: string | null; onPreview: (pid: string) => void }) {
  const total = Math.max(m.duration, 1);
  const placed = m.placements.filter((p) => !p.missing && p.start_s != null);
  return (
    <div className="mstrip" aria-hidden="true">
      <div className="mstrip-voice" />
      {placed.map((p) => {
        const left = (100 * p.start_s!) / total;
        const width = Math.max(1.2, (100 * ((p.end_s ?? p.start_s!) - p.start_s!)) / total);
        return (
          <button
            key={p.id}
            type="button"
            className={`mstrip-block role-${p.role} ${previewing === p.id ? "is-on" : ""}`}
            style={{ left: `${Math.min(left, 100 - width)}%`, width: `${width}%` }}
            title={`${p.role_label} · ${fmt(p.start_s!)} – ${fmt(p.end_s ?? 0)} · 点一下试听`}
            tabIndex={-1}
            onClick={() => onPreview(p.id)}
          >
            {p.role_label}
          </button>
        );
      })}
      <div className="mstrip-ticks small mono muted">
        <span>0:00</span>
        <span>{fmt(total / 2)}</span>
        <span>{fmt(total)}</span>
      </div>
    </div>
  );
}

export function MusicView({ id, onPauseMain }: { id: string; onPauseMain: () => void }) {
  const [m, setM] = useState<Music | null>(null);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [kindRoles, setKindRoles] = useState<Partial<Record<Kind, Role>>>({});
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [series, setSeries] = useState("洛城二三事");
  const clipRef = useRef<HTMLAudioElement | null>(null);
  const mixRef = useRef<HTMLAudioElement | null>(null);

  const load = useCallback(() => {
    Promise.all([libraryApi.music(id), libraryApi.library()])
      .then(([mm, lib]) => {
        setM(mm);
        setAssets(lib.assets);
        setKindRoles(lib.kind_roles);
        if (mm.series) setSeries(mm.series);
      })
      .catch((e) => setErr(String(e.message ?? e)));
  }, [id]);
  useEffect(load, [load]);

  const run = async (p: Promise<Music>, done?: string): Promise<boolean> => {
    try {
      const mm = await p;
      setM(mm);
      setMsg(mm.message ?? done ?? null);
      return true;
    } catch (e) {
      setMsg(`失败：${(e as Error).message}`);
      return false;
    }
  };

  const playPreview = (pid: string, draft = false) => {
    const a = clipRef.current;
    if (!a) return;
    const key = (draft ? "draft:" : "") + pid;
    if (preview === key) {
      a.pause();
      setPreview(null);
      return;
    }
    onPauseMain();
    mixRef.current?.pause();
    a.src = draft ? libraryApi.draftPreviewUrl(id, pid) : libraryApi.placementPreviewUrl(id, pid);
    setPreview(key);
    void a.play().catch(() => setPreview(null));
  };

  if (err) return <p className="error pad">{err}</p>;
  if (!m) return <p className="pad muted">加载中…</p>;
  return (
    <main className="home music">
      <header className="music-hero">
        <div className="grow">
          <h1>配乐</h1>
          <p className="muted small">
            <span className="mono">
              人声剪辑 {fmt(m.voice_duration)} → 成品 {fmt(m.duration)}
            </span>
            <span className="music-hero-sep">·</span>时间都按成品算；音乐会在人声下自动压低
          </p>
        </div>
        <div className="music-auto">
          <button type="button" className="btn btn-grad" onClick={() => void run(libraryApi.autoPlace(id))}>
            按用途自动放好
          </button>
          <span className="small muted">片头片尾直接放，间奏放在话题之间的停顿。先给建议，试听后再采用。</span>
        </div>
      </header>
      {msg && <p className="small note-line" data-testid="music-msg">{msg}</p>}
      {m.draft && (
        <DraftCard
          d={m.draft}
          previewing={preview?.startsWith("draft:") ? preview.slice(6) : null}
          onPreview={(pid) => playPreview(pid, true)}
          onMove={(pid, v) => void run(libraryApi.moveDraft(id, pid, v), "换好了位置，可以再试听")}
          onAccept={() => void run(libraryApi.acceptDraft(id, m.draft!.id), "已采用，导出会用这一版")}
          onDiscard={() => void run(libraryApi.discardDraft(id), "没有采用这条建议")}
        />
      )}
      {m.series_suggestion && (
        <div className="card banner-card row gap8 wrap" data-testid="series-suggestion">
          <span className="grow">系列「{m.series_suggestion.name}」有固定的片头片尾，要用在这一集吗？</span>
          <button type="button" className="btn btn-primary" onClick={() => void run(libraryApi.applySeries(id, m.series_suggestion!.name), "已放好系列片头片尾")}>
            用系列片头片尾
          </button>
          <button type="button" className="btn btn-outline" onClick={() => void run(libraryApi.dismissSeries(id))}>
            这一集不用
          </button>
        </div>
      )}
      <section className="card music-whole">
        <div className="card-head">
          <h2>成品试听（含配乐）</h2>
          <span className="small muted">导出也是这一版</span>
        </div>
        <MusicStrip m={m} previewing={preview} onPreview={(pid) => playPreview(pid)} />
        <audio
          ref={mixRef}
          controls
          preload="none"
          src={m.mix_url}
          data-testid="mix-audio"
          className="mix-audio"
          onPlay={() => {
            onPauseMain();
            clipRef.current?.pause();
            setPreview(null);
          }}
        />
      </section>
      <audio ref={clipRef} onEnded={() => setPreview(null)} data-testid="placement-audio" />
      <ul className="music-list">
        {m.placements.map((p) => (
          <PlacementRow
            key={p.id}
            p={p}
            previewing={preview === p.id}
            onPreview={() => playPreview(p.id)}
            onSave={(patch) => run(libraryApi.updatePlacement(id, p.id, patch), "已保存")}
            onRemove={() => void run(libraryApi.removePlacement(id, p.id), `已去掉${p.role_label}`)}
          />
        ))}
      </ul>
      {m.placements.length === 0 && <p className="muted">这一集还没有配乐。</p>}
      <MusicChatBox onSend={(text) => run(libraryApi.musicChat(id, text))} />
      <AddPlacement assets={assets} kindRoles={kindRoles} onAdd={(body) => run(libraryApi.addPlacement(id, body), "已放进去，可以点「试听这一处」")} />
      {m.placements.some((p) => p.role === "intro" || p.role === "outro") && (
        <div className="row gap8 wrap">
          <input value={series} onChange={(e) => setSeries(e.target.value)} aria-label="系列名" className="time" />
          <button type="button" className="btn btn-outline" onClick={() => void run(libraryApi.saveSeries(id, series), `已记住：以后「${series}」都用这个片头片尾`)}>
            记成系列片头片尾
          </button>
        </div>
      )}
      <div className="card">
        <h2>BGM 署名（show notes 会用）</h2>
        {m.credits.length === 0 ? (
          <p className="muted small">BGM：未设置</p>
        ) : (
          <ul className="credits" data-testid="credits">
            {m.credits.map((c, i) => (
              <li key={i}>
                <span className="mono small">{fmt(c.start_s)}</span> {c.role_label}：{c.credit_line}{" "}
                {c.credit_status !== "confirmed" && <span className={`badge badge-${c.credit_status}`}>{CREDIT_LABEL[c.credit_status]}</span>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </main>
  );
}
