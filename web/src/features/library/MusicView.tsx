import { useCallback, useEffect, useRef, useState } from "react";
import type { Asset, Kind, MusicView as Music, Placement, PlacementPatch, Role } from "./api";
import { fmt, parseTime } from "../../api";
import { CREDIT_LABEL } from "./LibraryView";
import { libraryApi } from "./api";
import { DraftCard, MusicChatBox } from "./MusicAssist";
import { t } from "../../i18n";
import { PageLoading } from "../loading/Loading";

const ROLE_HELP: Record<Role, string> = {
  intro: t("整首从头放：先只有音乐，然后压低当背景，人声进来，歌在背景里放完"),
  interlude: t("对话停下，音乐升起来正常音量放几秒，再压低当背景，对话接着来，歌放完为止"),
  outro: t("先压低垫在最后的对话下，说完拜拜升起来，放到结尾淡出"),
  bed: t("整段固定压低当背景，从你写的位置放到结束点"),
  clip: t("插入一段台词，前后各留一点空"),
};
const ANCHORED: Role[] = ["interlude", "bed", "clip"];
// the asset picker shows one short line per piece; the full credit is in the library and the credits list
const shortLabel = (t: string, max = 44) => (t.length > max ? `${t.slice(0, max - 1).trimEnd()}…` : t);

type Tune = "src_in_s" | "src_out_s" | "gain_db" | "solo_s" | "ramp_s" | "bg_db" | "pre_s" | "bye_s" | "fade_out_s";
type FieldDef = { k: Tune; label: string; time?: boolean; auto?: boolean };
// which numbers Leon sets for each use; times in the song accept 2:30 or 150
const FIELDS: Record<Role, FieldDef[]> = {
  intro: [
    { k: "solo_s", label: t("只放音乐（秒）") },
    { k: "bg_db", label: t("背景压低（dB）") },
    { k: "ramp_s", label: t("压低用时（秒）") },
  ],
  interlude: [
    { k: "solo_s", label: t("正常音量（秒）") },
    { k: "ramp_s", label: t("淡入淡出（秒）") },
    { k: "bg_db", label: t("背景压低（dB）") },
    { k: "pre_s", label: t("间隙前先垫（秒）") },
  ],
  outro: [
    { k: "bye_s", label: t("说拜拜在歌的"), time: true },
    { k: "ramp_s", label: t("升起用时（秒）") },
    { k: "bg_db", label: t("背景压低（dB）") },
    { k: "fade_out_s", label: t("结尾淡出（秒）"), auto: true },
  ],
  bed: [
    { k: "bg_db", label: t("背景压低（dB）") },
    { k: "fade_out_s", label: t("结尾淡出（秒）"), auto: true },
  ],
  clip: [],
};
const COMMON: FieldDef[] = [
  { k: "src_in_s", label: t("歌从"), time: true },
  { k: "src_out_s", label: t("裁到"), time: true },
];

const show = (v: number | null | undefined, time?: boolean) => (v == null ? "" : time ? fmt(v) : String(v));

/** One line in plain words: what Leon will hear for this piece of music. */
function describe(p: Placement): string {
  const whole = p.asset_duration_s != null && p.src_out_s >= p.asset_duration_s - 0.05 && p.src_in_s < 0.05;
  const len = whole ? t("整首 {p0}", { p0: fmt(p.src_out_s - p.src_in_s) }) : t("歌的 {p0}–{p1}", { p0: fmt(p.src_in_s), p1: fmt(p.src_out_s) });
  const bg = p.bg_db ?? 20;
  switch (p.role) {
    case "intro":
      return t("{len}：前 {solo} 秒只有音乐，再用 {ramp} 秒压低 {bg} dB，人声进来，歌在背景里放完", {
        len, solo: Math.min(p.solo_s ?? 0, p.src_out_s - p.src_in_s), ramp: p.ramp_s ?? 0, bg,
      });
    case "interlude":
      return t("{len}：对话停，{ramp} 秒淡入，正常音量 {solo} 秒，再 {ramp} 秒压低 {bg} dB，对话接着来，歌在背景里放完", {
        len, solo: p.solo_s ?? 0, ramp: p.ramp_s ?? 0, bg,
      });
    case "outro":
      return t("{len}：压低 {bg} dB 垫在对话下，你说拜拜时在歌的 {bye}，之后升起来，放到 {end} 结束", {
        len, bg, bye: fmt(p.bye_s ?? 0), end: fmt(p.src_out_s),
      });
    case "bed":
      return t("{len}：整段压低 {bg} dB 当背景", { len, bg });
    default:
      return len;
  }
}

function PlacementRow({ p, onSave, onRemove, onPreview, previewing }: {
  p: Placement;
  onSave: (patch: PlacementPatch) => Promise<boolean>;
  onRemove: () => void;
  onPreview: () => void;
  previewing: boolean;
}) {
  const fields = [...COMMON, ...FIELDS[p.role], { k: "gain_db" as Tune, label: t("音量（dB）") }];
  const fromP = () => Object.fromEntries(fields.map((f) => [f.k, show(p[f.k], f.time)])) as Record<Tune, string>;
  const key = fields.map((f) => p[f.k]).join("|");
  const [d, setD] = useState(fromP);
  useEffect(() => setD(fromP()), [key]); // eslint-disable-line react-hooks/exhaustive-deps
  const parsed = (f: FieldDef) => (f.time ? parseTime(d[f.k]) : d[f.k].trim() === "" ? null : Number(d[f.k]));
  const changed = fields.filter((f) => d[f.k] !== show(p[f.k], f.time));
  const bad = changed.some((f) => {
    const v = parsed(f);
    return (v == null && !f.auto) || (v != null && !isFinite(v));
  });
  const save = () => {
    const patch: PlacementPatch = {};
    for (const f of changed) {
      const v = parsed(f);
      if (v != null) patch[f.k] = v;
    }
    void onSave(patch);
  };
  const [pos, setPos] = useState(p.at_s != null ? fmt(p.at_s) : "");
  useEffect(() => setPos(p.at_s != null ? fmt(p.at_s) : ""), [p.at_s]);
  const moveTo = (t: number | null) => t != null && void onSave({ at_s: Math.max(0, Math.round(t * 1000) / 1000) });
  const [until, setUntil] = useState(p.until_at_s != null ? fmt(p.until_at_s) : "");
  useEffect(() => setUntil(p.until_at_s != null ? fmt(p.until_at_s) : ""), [p.until_at_s]);
  const untilTo = () => {
    const v = parseTime(until);
    if (v != null && (p.until_at_s == null || Math.abs(v - p.until_at_s) >= 1)) void onSave({ until_s: v });
  };
  return (
    <li className="card music-row" data-testid="placement">
      <div className="row gap12 wrap">
        <span className={`chip role-chip role-${p.role}`}>{p.role_label}</span>
        <strong className="grow">{p.missing ? t("素材已不在库里") : p.asset_name}</strong>
        {p.start_s != null && (
          <span className="mono small">
            {fmt(p.start_s)} – {fmt(p.end_s ?? 0)}
            {p.inserted_s ? t(" · 插入 {p0} 秒", { p0: p.inserted_s.toFixed(1) }) : ""}
          </span>
        )}
      </div>
      <div className="row gap8 wrap small">
        <span>{t("BGM 署名：")}{p.credit_line}</span>
        {p.credit_status && <span className={`badge badge-${p.credit_status}`}>{CREDIT_LABEL[p.credit_status]}</span>}
      </div>
      {!p.missing && p.start_s != null && (
        <p className="small muted music-plan" data-testid="placement-plan">
          {describe(p)}
        </p>
      )}
      {!p.missing && (
        <div className="row gap12 wrap music-tune">
          {fields.map((f) => (
            <label key={f.k} className="row gap8 small">
              {f.label}
              <input
                className={f.time ? "time" : "num"}
                inputMode="decimal"
                value={d[f.k]}
                placeholder={f.auto ? t("自动") : f.time ? "2:30" : ""}
                onChange={(e) => setD({ ...d, [f.k]: e.target.value })}
                onKeyDown={(e) => e.key === "Enter" && changed.length > 0 && !bad && save()}
                aria-label={f.label}
              />
            </label>
          ))}
          <button type="button" className="btn btn-small" disabled={!changed.length || bad} onClick={save}>
            {t("保存")}
          </button>
        </div>
      )}
      <div className="row gap8 wrap">
        {ANCHORED.includes(p.role) && p.at_s != null && (
          <span className="row gap4 wrap small" data-testid="placement-position">
            {t("位置")}
            <input
              className="time"
              value={pos}
              onChange={(e) => setPos(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && moveTo(parseTime(pos))}
              onBlur={() => parseTime(pos) !== null && parseTime(pos) !== Math.floor(p.at_s!) && moveTo(parseTime(pos))}
              aria-label={t("位置（成品时间）")}
            />
            <button type="button" className="btn btn-small btn-outline" onClick={() => moveTo(p.at_s! - 1)}>
              {t("早 1 秒")}
            </button>
            <button type="button" className="btn btn-small btn-outline" onClick={() => moveTo(p.at_s! + 1)}>
              {t("晚 1 秒")}
            </button>
            {p.role === "bed" && (
              <>
                {t("到")}
                <input
                  className="time"
                  value={until}
                  placeholder={t("歌放完")}
                  onChange={(e) => setUntil(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && untilTo()}
                  onBlur={untilTo}
                  aria-label={t("铺到（成品时间）")}
                />
              </>
            )}
          </span>
        )}
        <span className="grow" />
        {!p.missing && p.start_s != null && (
          <button type="button" className="btn btn-small btn-outline" onClick={onPreview} aria-pressed={previewing}>
            {previewing ? t("停止") : t("试听这一处")}
          </button>
        )}
        <button type="button" className="btn btn-small btn-outline" onClick={onRemove}>
          {t("去掉")}
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
        {t("素材库里还没有音乐。先去")} <a href="#/library">{t("素材库")}</a> {t("添加片头、配乐或台词。")}
      </p>
    );
  const add = () => {
    const body: PlacementPatch & { asset_id: string; role: Role } = { asset_id: assetId, role };
    if (ANCHORED.includes(role)) {
      const atS = parseTime(at);
      if (atS == null) {
        setErr(t("请写位置，比如 45:59（成品时间）"));
        return;
      }
      body.at_s = atS;
      const u = role === "bed" ? parseTime(until) : null;
      if (u != null) body.until_s = u;
    }
    setErr(null);
    void onAdd(body).then((ok) => ok && setAt(""));
  };
  return (
    <div className="card music-add">
      <h2>{t("放一段音乐")}</h2>
      <div className="row gap8 wrap">
        <select
          value={assetId}
          onChange={(e) => {
            setAssetId(e.target.value); // the asset's use in the library decides where it goes
            setRole(roleOf(e.target.value));
          }}
          aria-label={t("选择素材")}
          className="music-pick"
        >
          {assets.map((a) => (
            <option key={a.id} value={a.id}>
              {shortLabel(a.credit_line !== a.name.replace(/\.[^.]+$/, "") ? a.credit_line : a.name)} · {a.kind_label}
            </option>
          ))}
        </select>
        <select value={role} onChange={(e) => setRole(e.target.value as Role)} aria-label={t("用途")}>
          <option value="intro">{t("片头")}</option>
          <option value="interlude">{t("间奏 / 休息间隙")}</option>
          <option value="outro">{t("片尾")}</option>
          <option value="bed">{t("铺底")}</option>
          <option value="clip">{t("台词")}</option>
        </select>
        {ANCHORED.includes(role) && (
          <input className="time" value={at} onChange={(e) => setAt(e.target.value)} placeholder={t("位置 45:59")} aria-label={t("位置")} />
        )}
        {role === "bed" && (
          <input className="time" value={until} onChange={(e) => setUntil(e.target.value)} placeholder={t("到 47:00（可空）")} aria-label={t("铺到")} />
        )}
        <button type="button" className="btn btn-primary" onClick={add}>
          {t("放进去")}
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
            title={t("{role_label} · {p1} – {p2} · 点一下试听", { role_label: p.role_label, p1: fmt(p.start_s!), p2: fmt(p.end_s ?? 0) })}
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
  const [series, setSeries] = useState("洛城二三事"); // i18n-ignore
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
      setMsg(t("失败：{message}", { message: (e as Error).message }));
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
  if (!m) return <PageLoading label={t("正在打开配乐…")} />;
  return (
    <main className="home music">
      <header className="music-hero">
        <div className="grow">
          <h1>{t("配乐")}</h1>
          <p className="muted small">
            <span className="mono">
              {t("人声剪辑 {voice} → 成品 {final}", { voice: fmt(m.voice_duration), final: fmt(m.duration) })}
            </span>
            <span className="music-hero-sep">·</span>{t("时间都按成品算；歌都整首放完，有人说话时压低当背景")}
          </p>
        </div>
        <div className="music-auto">
          <button type="button" className="btn btn-grad" onClick={() => void run(libraryApi.autoPlace(id))}>
            {t("按用途自动放好")}
          </button>
          <span className="small muted">{t("片头片尾直接放，间奏放在话题之间的停顿。先给建议，试听后再采用。")}</span>
        </div>
      </header>
      {msg && <p className="small note-line" data-testid="music-msg">{msg}</p>}
      {m.draft && (
        <DraftCard
          d={m.draft}
          previewing={preview?.startsWith("draft:") ? preview.slice(6) : null}
          onPreview={(pid) => playPreview(pid, true)}
          onMove={(pid, v) => void run(libraryApi.moveDraft(id, pid, v), t("换好了位置，可以再试听"))}
          onAccept={() => void run(libraryApi.acceptDraft(id, m.draft!.id), t("已采用，导出会用这一版"))}
          onDiscard={() => void run(libraryApi.discardDraft(id), t("没有采用这条建议"))}
        />
      )}
      {m.series_suggestion && (
        <div className="card banner-card row gap8 wrap" data-testid="series-suggestion">
          <span className="grow">{t("系列「{name}」有固定的片头片尾，要用在这一集吗？", { name: m.series_suggestion.name })}</span>
          <button type="button" className="btn btn-primary" onClick={() => void run(libraryApi.applySeries(id, m.series_suggestion!.name), t("已放好系列片头片尾"))}>
            {t("用系列片头片尾")}
          </button>
          <button type="button" className="btn btn-outline" onClick={() => void run(libraryApi.dismissSeries(id))}>
            {t("这一集不用")}
          </button>
        </div>
      )}
      <section className="card music-whole">
        <div className="card-head">
          <h2>{t("成品试听（含配乐）")}</h2>
          <span className="small muted">{t("导出也是这一版")}</span>
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
            onSave={(patch) => run(libraryApi.updatePlacement(id, p.id, patch), t("已保存"))}
            onRemove={() => void run(libraryApi.removePlacement(id, p.id), t("已去掉{role_label}", { role_label: p.role_label }))}
          />
        ))}
      </ul>
      {m.placements.length === 0 && <p className="muted">{t("这一集还没有配乐。")}</p>}
      <MusicChatBox onSend={(text) => run(libraryApi.musicChat(id, text))} />
      <AddPlacement assets={assets} kindRoles={kindRoles} onAdd={(body) => run(libraryApi.addPlacement(id, body), t("已放进去，可以点「试听这一处」"))} />
      {m.placements.some((p) => p.role === "intro" || p.role === "outro") && (
        <div className="row gap8 wrap">
          <input value={series} onChange={(e) => setSeries(e.target.value)} aria-label={t("系列名")} className="time" />
          <button type="button" className="btn btn-outline" onClick={() => void run(libraryApi.saveSeries(id, series), t("已记住：以后「{series}」都用这个片头片尾", { series }))}>
            {t("记成系列片头片尾")}
          </button>
        </div>
      )}
      <div className="card">
        <h2>{t("BGM 署名（show notes 会用）")}</h2>
        {m.credits.length === 0 ? (
          <p className="muted small">{t("BGM：未设置")}</p>
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
