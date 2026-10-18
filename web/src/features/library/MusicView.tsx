import { useCallback, useEffect, useRef, useState } from "react";
import type { Asset, Kind, MusicView as Music, Placement, PlacementPatch, Role } from "./api";
import { fmt, parseTime } from "../../api";
import { CREDIT_LABEL } from "./LibraryView";
import { libraryApi } from "./api";
import { DraftCard, MusicChatBox } from "./MusicAssist";
import { EpisodeUpload } from "./Scope";
import { t } from "../../i18n";
import { PageLoading } from "../loading/Loading";

const ROLE_HELP: Record<Role, string> = {
  intro: t("整首从头放：先只有音乐，然后压低当背景，人声进来，歌在背景里放完"),
  interlude: t("对话停下，音乐升起来全音量放几秒，再压低当背景，对话接着来，歌放完为止"),
  outro: t("先压低垫在最后的对话下，说完拜拜升起来，放到结尾淡出"),
  bed: t("整段固定压低当背景。位置空着就由 App 放进没有其他配乐的空档；写了位置就从那里放"),
  clip: t("插入一段台词，前后各留一点空"),
};
const ANCHORED: Role[] = ["interlude", "bed", "clip"];
const ROLES: Role[] = ["intro", "interlude", "outro", "bed", "clip"];
const ROLE_NAME: Record<Role, string> = {
  intro: t("片头"),
  interlude: t("间奏 / 休息间隙"),
  outro: t("片尾"),
  bed: t("铺底"),
  clip: t("台词"),
};
const BG_DEFAULT = 22; // dB, new placements (lacuna_app/music.py BG_DB)
const SKIP_S = 5;
const shortLabel = (t: string, max = 44) => (t.length > max ? `${t.slice(0, max - 1).trimEnd()}…` : t);
/** One line per piece in the asset picker: the file name always first and never shortened, then the
 * song (when it is known by more than its file name) and its use. */
export function assetLabel(a: Pick<Asset, "name" | "credit_line" | "kind_label">): string {
  const stem = a.name.replace(/\.[^.]+$/, "");
  const song = a.credit_line && a.credit_line !== stem && a.credit_line !== a.name ? ` - ${shortLabel(a.credit_line)}` : "";
  return `${a.name}${song} · ${a.kind_label}`;
}

type Tune = "src_in_s" | "src_out_s" | "gain_db" | "solo_s" | "ramp_s" | "ramp_out_s" | "bg_db" | "pre_s" | "bye_s" | "fade_out_s";
type FieldDef = { k: Tune; label: string; time?: boolean; auto?: boolean };
// which numbers Leon sets for each use; times in the song accept 2:30 or 150
const FIELDS: Record<Role, FieldDef[]> = {
  intro: [
    { k: "solo_s", label: t("只放音乐（秒）") },
    { k: "bg_db", label: t("背景压低（dB）") },
    { k: "ramp_s", label: t("压低用时（秒）") },
  ],
  interlude: [
    { k: "ramp_s", label: t("淡入（秒）") },
    { k: "solo_s", label: t("全音量时长（秒）") },
    { k: "ramp_out_s", label: t("淡出到背景（秒）") },
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
  const bg = p.bg_db ?? BG_DEFAULT;
  switch (p.role) {
    case "intro":
      return t("{len}：前 {solo} 秒只有音乐，再用 {ramp} 秒压低 {bg} dB，人声进来，歌在背景里放完", {
        len, solo: Math.min(p.solo_s ?? 0, p.src_out_s - p.src_in_s), ramp: p.ramp_s ?? 0, bg,
      });
    case "interlude":
      return t("{len}：对话停，{ramp} 秒淡入，全音量 {solo} 秒，再 {out} 秒压低 {bg} dB，对话接着来，歌在背景里放完", {
        len, solo: p.solo_s ?? 0, ramp: p.ramp_s ?? 0, out: p.ramp_out_s ?? p.ramp_s ?? 0, bg,
      });
    case "outro":
      return t("{len}：压低 {bg} dB 垫在对话下，你说拜拜时在歌的 {bye}，之后升起来，放到 {end} 结束", {
        len, bg, bye: fmt(p.bye_s ?? 0), end: fmt(p.src_out_s),
      });
    case "bed":
      return (
        (p.auto ? t("{len}：App 放在没有其他配乐的空档，整段压低 {bg} dB 当背景", { len, bg }) : t("{len}：整段压低 {bg} dB 当背景", { len, bg })) +
        (p.loop ? t("，循环填满这一段") : "")
      );
    default:
      return len;
  }
}

function PlacementRow({ p, taken, onSave, onRemove, onPreview, previewing }: {
  p: Placement;
  taken: Role[]; // uses of the other placements (one intro, one outro)
  onSave: (patch: PlacementPatch, done?: string) => Promise<boolean>;
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
    <li className="card music-row" data-testid="placement" data-role={p.role}>
      <div className="row gap12 wrap">
        {p.missing ? (
          <span className={`chip role-chip role-${p.role}`}>{p.role_label}</span>
        ) : (
          <select
            className={`chip-select role-select role-${p.role}`}
            value={p.role}
            aria-label={t("改类型")}
            title={t("改类型：歌、裁剪和音量都保留")}
            onChange={(e) => {
              const role = e.target.value as Role;
              void onSave({ role }, t("已改成{role}", { role: ROLE_NAME[role] }));
            }}
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {r !== p.role && (r === "intro" || r === "outro") && taken.includes(r) ? t("{role}（替换现在的）", { role: ROLE_NAME[r] }) : ROLE_NAME[r]}
              </option>
            ))}
          </select>
        )}
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
      {p.no_room && (
        <p className="small warn-line" data-testid="placement-no-room">
          {t("没有空档可放：别的配乐已经把时间占满了。可以写一个位置手动放，或者去掉别的配乐。")}
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
      {!p.missing && p.level_db != null && (
        <p className="small muted" data-testid="placement-level">
          {t("已自动调平 {db} dB，和人声相称；「音量（dB）」是在这之上的微调。", {
            db: `${p.level_db > 0 ? "+" : p.level_db < 0 ? "−" : "±"}${Math.abs(p.level_db).toFixed(1)}`,
          })}
        </p>
      )}
      {p.role === "bed" && !p.missing && (
        <div className="row gap12 wrap small" data-testid="bed-options">
          <label className="check">
            <input
              type="checkbox"
              checked={!!p.auto}
              onChange={(e) =>
                void onSave(
                  e.target.checked ? { auto: true } : { auto: false, at_s: p.at_s ?? 0 },
                  e.target.checked ? t("已改成自动放进空档") : t("已固定在现在的位置"),
                )
              }
            />
            {t("自动放进空档")}
          </label>
          <label className="check">
            <input type="checkbox" checked={!!p.loop} onChange={(e) => void onSave({ loop: e.target.checked }, t("已保存"))} />
            {t("循环填满")}
          </label>
        </div>
      )}
      <div className="row gap8 wrap">
        {ANCHORED.includes(p.role) && (p.at_s != null || p.role === "bed") && !p.missing && (
          <span className="row gap4 wrap small" data-testid="placement-position">
            {t("位置")}
            <input
              className="time"
              value={pos}
              placeholder={p.auto ? t("自动") : ""}
              onChange={(e) => setPos(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && moveTo(parseTime(pos))}
              onBlur={() => parseTime(pos) !== null && (p.at_s == null || parseTime(pos) !== Math.floor(p.at_s)) && moveTo(parseTime(pos))}
              aria-label={t("位置（成品时间）")}
            />
            {p.at_s != null && (
              <>
                <button type="button" className="btn btn-small btn-outline" onClick={() => moveTo(p.at_s! - 1)}>
                  {t("早 1 秒")}
                </button>
                <button type="button" className="btn btn-small btn-outline" onClick={() => moveTo(p.at_s! + 1)}>
                  {t("晚 1 秒")}
                </button>
              </>
            )}
            {p.role === "bed" && !p.auto && (
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
  const [loop, setLoop] = useState(false);
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
      if (atS == null && role !== "bed") {
        setErr(t("请写位置，比如 45:59（成品时间）"));
        return;
      }
      if (atS != null) body.at_s = atS; // a bed without a position goes into the free stretches
      const u = role === "bed" && atS != null ? parseTime(until) : null;
      if (u != null) body.until_s = u;
    }
    if (role === "bed") body.loop = loop;
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
              {assetLabel(a)}
            </option>
          ))}
        </select>
        <select value={role} onChange={(e) => setRole(e.target.value as Role)} aria-label={t("用途")}>
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {ROLE_NAME[r]}
            </option>
          ))}
        </select>
        {ANCHORED.includes(role) && (
          <input
            className={role === "bed" ? "time time-wide" : "time"}
            value={at}
            onChange={(e) => setAt(e.target.value)}
            placeholder={role === "bed" ? t("位置（空着 = 自动放进空档）") : t("位置 45:59")}
            aria-label={t("位置")}
          />
        )}
        {role === "bed" && at.trim() !== "" && (
          <input className="time" value={until} onChange={(e) => setUntil(e.target.value)} placeholder={t("到 47:00（可空）")} aria-label={t("铺到")} />
        )}
        {role === "bed" && (
          <label className="check small">
            <input type="checkbox" checked={loop} onChange={(e) => setLoop(e.target.checked)} aria-label={t("循环填满")} />
            {t("循环填满")}
          </label>
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

/** The whole final episode at a glance: the voice, each piece of music where it sits, and where the
 * player below is. Click a block to hear it there, or anywhere else on the strip to jump to that point. */
function MusicStrip({ m, now, previewing, onListen, onSeek }: {
  m: Music;
  now: number;
  previewing: string | null;
  onListen: (p: Placement) => void;
  onSeek: (t: number) => void;
}) {
  const total = Math.max(m.duration, 1);
  const placed = m.placements.filter((p) => !p.missing && p.start_s != null);
  return (
    <div
      className="mstrip"
      data-testid="mstrip"
      onClick={(e) => {
        const r = e.currentTarget.getBoundingClientRect();
        onSeek((Math.min(Math.max(e.clientX - r.left, 0), r.width) / Math.max(r.width, 1)) * total);
      }}
    >
      <div className="mstrip-voice" />
      {placed.map((p) => {
        const left = (100 * p.start_s!) / total;
        const width = Math.max(1.2, (100 * ((p.end_s ?? p.start_s!) - p.start_s!)) / total);
        return (
          <button
            key={p.id}
            type="button"
            data-testid="mstrip-block"
            className={`mstrip-block role-${p.role} ${previewing === p.id ? "is-on" : ""}`}
            style={{ left: `${Math.min(left, 100 - width)}%`, width: `${width}%` }}
            title={t("{role_label} · {p1} – {p2} · 点一下从这里听", { role_label: p.role_label, p1: fmt(p.start_s!), p2: fmt(p.end_s ?? 0) })}
            onClick={(e) => {
              e.stopPropagation();
              onListen(p);
            }}
          >
            {p.role_label}
          </button>
        );
      })}
      <div className="mstrip-head" data-testid="mstrip-head" style={{ left: `${Math.min((100 * now) / total, 100)}%` }} />
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
  const [kinds, setKinds] = useState<Record<string, string>>({});
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [series, setSeries] = useState("洛城二三事"); // i18n-ignore
  const clipRef = useRef<HTMLAudioElement | null>(null); // a suggestion's preview (not in the mix yet)
  const mixRef = useRef<HTMLAudioElement | null>(null); // the one player for the episode's music
  const [now, setNow] = useState(0);
  const [playing, setPlaying] = useState(false);
  const shownMix = useRef<string | null>(null);

  const load = useCallback(() => {
    // only what this episode may use: shared (公共) assets and its own (本集)
    Promise.all([libraryApi.music(id), libraryApi.library(id)])
      .then(([mm, lib]) => {
        setM(mm);
        setAssets(lib.assets);
        setKinds(lib.kinds);
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

  // a suggestion is heard as a short clip around it; it is not part of the episode's mix yet
  const playPreview = (pid: string) => {
    const a = clipRef.current;
    if (!a) return;
    const key = "draft:" + pid;
    if (preview === key) {
      a.pause();
      setPreview(null);
      return;
    }
    onPauseMain();
    mixRef.current?.pause();
    a.src = libraryApi.draftPreviewUrl(id, pid);
    setPreview(key);
    void a.play().catch(() => setPreview(null));
  };

  /** Move the episode player to `at` (final-mix seconds); the strip follows it. */
  const seekMix = (at: number, play: boolean) => {
    const a = mixRef.current;
    if (!a || !m) return;
    const to = Math.min(Math.max(at, 0), m.duration);
    setNow(to);
    const go = () => {
      a.currentTime = to;
      if (play) void a.play().catch(() => setPlaying(false));
    };
    if (a.readyState >= 1) go();
    else {
      a.addEventListener("loadedmetadata", go, { once: true });
      a.load();
    }
  };
  // 「试听这一处」 and the strip's blocks: the player below jumps to just before the transition and plays
  const listen = (p: Placement) => {
    if (preview === p.id && playing) {
      mixRef.current?.pause();
      return;
    }
    clipRef.current?.pause();
    onPauseMain();
    setPreview(p.id);
    seekMix(p.listen_s ?? p.start_s ?? 0, true);
  };
  const skip = (d: number) => seekMix((mixRef.current?.currentTime ?? now) + d, playing);

  // a new mix (after a change) keeps the listening position
  useEffect(() => {
    if (!m) return;
    if (shownMix.current && shownMix.current !== m.mix_url && now > 0) seekMix(now, false);
    shownMix.current = m.mix_url;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [m?.mix_url]);

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
          onPreview={(pid) => playPreview(pid)}
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
        <MusicStrip
          m={m}
          now={now}
          previewing={playing ? preview : null}
          onListen={listen}
          onSeek={(at) => {
            setPreview(null);
            seekMix(at, true);
          }}
        />
        <audio
          ref={mixRef}
          controls
          preload="none"
          src={m.mix_url}
          data-testid="mix-audio"
          className="mix-audio"
          onPlay={() => {
            onPauseMain();
            if (preview?.startsWith("draft:")) setPreview(null);
            clipRef.current?.pause();
            setPlaying(true);
          }}
          onPause={() => {
            setPlaying(false);
            setPreview(null);
          }}
          onTimeUpdate={(e) => setNow(e.currentTarget.currentTime)}
          onSeeked={(e) => setNow(e.currentTarget.currentTime)}
        />
        <div className="row gap8 wrap mix-controls">
          <button type="button" className="btn btn-small btn-outline" onClick={() => skip(-SKIP_S)} aria-label={t("后退 5 秒")}>
            {t("−5 秒")}
          </button>
          <button type="button" className="btn btn-small btn-outline" onClick={() => skip(SKIP_S)} aria-label={t("前进 5 秒")}>
            {t("+5 秒")}
          </button>
          <span className="mono small muted" data-testid="mix-clock">
            {fmt(now)} / {fmt(m.duration)}
          </span>
        </div>
      </section>
      <audio ref={clipRef} onEnded={() => setPreview(null)} data-testid="placement-audio" />
      <ul className="music-list">
        {m.placements.map((p) => (
          <PlacementRow
            key={`${p.id}:${p.role}`} // a new type has other fields: start the row afresh
            p={p}
            taken={m.placements.filter((x) => x.id !== p.id).map((x) => x.role)}
            previewing={playing && preview === p.id}
            onPreview={() => listen(p)}
            onSave={(patch, done) => run(libraryApi.updatePlacement(id, p.id, patch), done ?? t("已保存"))}
            onRemove={() => void run(libraryApi.removePlacement(id, p.id), t("已去掉{role_label}", { role_label: p.role_label }))}
          />
        ))}
      </ul>
      {m.placements.length === 0 && <p className="muted">{t("这一集还没有配乐。")}</p>}
      <MusicChatBox onSend={(text) => run(libraryApi.musicChat(id, text))} />
      <AddPlacement assets={assets} kindRoles={kindRoles} onAdd={(body) => run(libraryApi.addPlacement(id, body), t("已放进去，可以点「试听这一处」"))} />
      <EpisodeUpload
        id={id}
        kinds={kinds}
        onAdded={(text) => {
          setMsg(text);
          libraryApi
            .library(id)
            .then((lib) => setAssets(lib.assets))
            .catch((e) => setErr(String(e.message ?? e)));
        }}
      />
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
