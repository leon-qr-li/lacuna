import { useCallback, useEffect, useRef, useState } from "react";
import type { Asset, Kind, MusicView as Music, Placement, PlacementPatch, Role } from "./api";
import "./music-b.css";
import { fmt, parseTime } from "../../api";
import { CREDIT_LABEL } from "./LibraryView";
import { libraryApi } from "./api";
import { ANCHORED, PlacementCard, ROLE_HELP, ROLE_NAME, ROLES } from "./MusicCard";
import { MusicLibrary } from "./MusicLibrary";
import { DraftCard, MusicChatBox } from "./MusicAssist";
import { EpisodeUpload } from "./Scope";
import { t } from "../../i18n";
import { PageLoading } from "../loading/Loading";
import { SpeedButton } from "../review-speed/SpeedButton";
import { useRate } from "../review-speed/speed";
import { GapBanner, StripGaps } from "../gaps/Gaps";
import { gapsApi } from "../gaps/api";

const SKIP_S = 5;
const shortLabel = (t: string, max = 44) => (t.length > max ? `${t.slice(0, max - 1).trimEnd()}…` : t);
/** One line per piece in the asset picker: the file name always first and never shortened, then the
 * song (when it is known by more than its file name) and its use. */
export function assetLabel(a: Pick<Asset, "name" | "credit_line" | "kind_label">): string {
  const stem = a.name.replace(/\.[^.]+$/, "");
  const song = a.credit_line && a.credit_line !== stem && a.credit_line !== a.name ? ` - ${shortLabel(a.credit_line)}` : "";
  return `${a.name}${song} · ${a.kind_label}`;
}

const GROUPS: ["episode" | "album" | "project", (album: string | null) => string][] = [
  ["episode", () => t("只这一集")],
  ["album", (album) => (album ? t("专辑「{name}」", { name: album }) : t("本专辑"))],
  ["project", () => t("整个节目")],
];

function AddPlacement({ assets, albumName, kindRoles, pick, onAdd }: {
  assets: Asset[];
  /** the album this episode is in, for the 「专辑」 group's label */
  albumName: string | null;
  kindRoles: Partial<Record<Kind, Role>>;
  /** a file just added on this page: picked, ready to 放进去 */
  pick?: string;
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
  useEffect(() => {
    if (pick && assets.find((a) => a.id === pick)) {
      setAssetId(pick);
      setRole(roleOf(pick));
    }
  }, [pick, assets]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!assets.length)
    return (
      <p className="muted" data-testid="music-no-assets">
        {t("这一集还没有能用的素材。可以在下面「从电脑添加」，或者去")} <a href="#/library">{t("素材库")}</a>{" "}
        {t("把素材设为公共、或加到这一集。")}
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
    <div className="music-add" data-tour="music-add">
      <h3>{t("按时间放一段")}</h3>
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
          {/* nearest first: this episode's own, its album's, the whole project's */}
          {GROUPS.map(([g, label]) => {
            const mine = assets.filter((a) => (a.group ?? "project") === g);
            return (
              mine.length > 0 && (
                <optgroup key={g} label={label(albumName)}>
                  {mine.map((a) => (
                    <option key={a.id} value={a.id}>
                      {assetLabel(a)}
                    </option>
                  ))}
                </optgroup>
              )
            );
          })}
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
      <StripGaps list={m.gaps} total={total} />
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
  const [libraryEmpty, setLibraryEmpty] = useState(false);
  const [kindRoles, setKindRoles] = useState<Partial<Record<Kind, Role>>>({});
  const [kinds, setKinds] = useState<Record<string, string>>({});
  const [picked, setPicked] = useState<string | undefined>(); // the file just added on this page
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [albumName, setAlbumName] = useState<string | null>(null); // the album this episode is in
  const clipRef = useRef<HTMLAudioElement | null>(null); // a suggestion's preview (not in the mix yet)
  const mixRef = useRef<HTMLAudioElement | null>(null); // the one player for the episode's music
  const [now, setNow] = useState(0);
  const speed = useRate("lacuna.musicRate"); // 验收 V8: speed on the mix player, pitch kept
  const [playing, setPlaying] = useState(false);
  const shownMix = useRef<string | null>(null);
  const [sel, setSel] = useState<string | null>(null); // the open card
  const [more, setMore] = useState(false); // 更多设置 on the open card
  const [scope, setScope] = useState<"episode" | "album" | "project">("project");

  const load = useCallback(() => {
    // only what this episode may use: the whole project's, its album's and its own
    Promise.all([libraryApi.music(id), libraryApi.library(id)])
      .then(([mm, lib]) => {
        setM(mm);
        setAssets(lib.assets);
        setKinds(lib.kinds);
        setKindRoles(lib.kind_roles);
        setAlbumName(lib.albums.find((a) => a.id === lib.album)?.name ?? null);
        // the empty-state card is for a library with nothing at all, not one whose files belong elsewhere
        if (!lib.assets.length) libraryApi.library().then((all) => setLibraryEmpty(!all.assets.length), () => setLibraryEmpty(false));
        else setLibraryEmpty(false);
      })
      .catch((e) => setErr(String(e.message ?? e)));
  }, [id]);
  useEffect(load, [load]);
  // 入门: 加片头和片尾音乐 is done once this episode has both

  // the open card: the one just put in, else the one that was open, else the first
  useEffect(() => {
    if (!m) return;
    if (!sel || !m.placements.some((p) => p.id === sel)) setSel(m.placements[0]?.id ?? null);
  }, [m, sel]);
  useEffect(() => {
    if (albumName) setScope("album");
  }, [albumName]);

  const run = async (p: Promise<Music>, done?: string): Promise<boolean> => {
    try {
      const before = new Set(m?.placements.map((x) => x.id));
      const mm = await p;
      const fresh = mm.placements.find((x) => !before.has(x.id));
      if (fresh) setSel(fresh.id);
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

  // the element mounts with the page and a new mix reloads it: (re)apply the chosen speed each time
  const applyRate = useCallback(() => {
    const a = mixRef.current;
    if (!a) return;
    a.preservesPitch = true;
    a.defaultPlaybackRate = speed.rate;
    a.playbackRate = speed.rate;
  }, [speed.rate]);
  useEffect(applyRate, [applyRate, m?.mix_url]);

  if (err) return <p className="error pad">{err}</p>;
  if (!m) return <PageLoading label={t("正在打开配乐…")} />;
  // nothing to place yet (a new user's empty library): start with adding music, not a dead-end button
  const empty = libraryEmpty && assets.length === 0 && m.placements.length === 0;
  const upload = (
    <EpisodeUpload
      id={id}
      kinds={kinds}
      onAdded={(text, asset) => {
        setMsg(text);
        libraryApi
          .library(id)
          .then((lib) => {
            setAssets(lib.assets);
            setLibraryEmpty(false);
            if (asset) setPicked(asset.id);
          })
          .catch((e) => setErr(String(e.message ?? e)));
      }}
    />
  );
  const taken = m.placements.map((x) => x.role);
  const ends = m.placements.some((p) => p.role === "intro" || p.role === "outro");
  const saveDefaults = () => {
    if (scope === "album" && albumName)
      void run(libraryApi.saveSeries(id, "album"), t("已记住：专辑「{name}」以后的新剧集都用这个片头片尾", { name: albumName }));
    else if (scope === "project") void run(libraryApi.saveSeries(id, "project"), t("已记住：这个节目以后的新剧集都用这个片头片尾"));
  };
  return (
    <main className="home music music-b">
      <header className="music-hero">
        <div className="grow">
          <h1 className="step-title">{t("配乐")}</h1>
          <p className="muted small">
            <span className="mono">
              {t("人声剪辑 {voice} → 成品 {final}", { voice: fmt(m.voice_duration), final: fmt(m.duration) })}
            </span>
            <span className="music-hero-sep">·</span>{t("时间都按成品算；歌都整首放完，有人说话时压低当背景")}
          </p>
        </div>
      </header>
      {empty && (
        <section className="card music-empty" data-testid="music-empty">
          <h2>{t("先加片头和片尾音乐")}</h2>
          <p className="muted small">{t("素材库还是空的。从电脑添加音乐文件后，就能把它放进这一集。请只用你有权使用的音乐。")}</p>
          {upload}
        </section>
      )}
      <div className={`music-grid${empty ? " is-empty" : ""}`}>
        {!empty && (
          <MusicLibrary
            assets={assets}
            taken={taken}
            now={now}
            upload={upload}
            onPauseOthers={() => {
              onPauseMain();
              mixRef.current?.pause();
              clipRef.current?.pause();
            }}
            onPlace={(body) => void run(libraryApi.addPlacement(id, body), t("已放进去，可以点「试听这一处」"))}
          >
            <AddPlacement assets={assets} albumName={albumName} kindRoles={kindRoles} pick={picked} onAdd={(body) => run(libraryApi.addPlacement(id, body), t("已放进去，可以点「试听这一处」"))} />
          </MusicLibrary>
        )}
        <div className="music-main">
          {!empty && (
            <div className="music-bar" data-tour="music-toolbar">
              <span className="row gap8 music-scope" data-testid="save-scope">
                <span className="small muted">{t("用在")}</span>
                <span className="seg" role="radiogroup" aria-label={t("片头片尾用在")}>
                  {(["episode", ...(albumName ? ["album"] : []), "project"] as const).map((k) => (
                    <button
                      key={k}
                      type="button"
                      role="radio"
                      aria-checked={scope === k}
                      className={scope === k ? "is-on" : ""}
                      onClick={() => setScope(k as typeof scope)}
                    >
                      {k === "episode" ? t("只这一集") : k === "album" ? t("专辑「{name}」", { name: albumName ?? "" }) : t("整个节目")}
                    </button>
                  ))}
                </span>
              </span>
              <span className="grow" />
              <button type="button" className="btn btn-outline btn-small" onClick={() => void run(libraryApi.autoPlace(id))} title={t("片头片尾直接放，间奏放在话题之间的停顿。先给建议，试听后再采用。")}>
                {t("按用途自动放好")}
              </button>
              {ends && (
                <button
                  type="button"
                  className="btn btn-outline btn-small"
                  data-testid="save-defaults"
                  data-tour="music-default"
                  disabled={scope === "episode"}
                  title={scope === "episode" ? t("现在选的是「只这一集」：不改以后的剧集") : undefined}
                  onClick={saveDefaults}
                >
                  {t("设为默认片头片尾")}
                </button>
              )}
            </div>
          )}
          <GapBanner list={m.gaps} onFill={() => void run(gapsApi.fill(id))} />
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
              <span className="grow">
                {m.series_suggestion.name
                  ? t("专辑「{name}」有默认的片头片尾，要用在这一集吗？", { name: m.series_suggestion.name })
                  : t("这个节目有默认的片头片尾，要用在这一集吗？")}
                {(m.series_suggestion.intro || m.series_suggestion.outro) && (
                  <span className="small muted series-files">
                    {[
                      m.series_suggestion.intro && t("片头：{name}", { name: m.series_suggestion.intro }),
                      m.series_suggestion.outro && t("片尾：{name}", { name: m.series_suggestion.outro }),
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                )}
              </span>
              <button type="button" className="btn btn-primary" onClick={() => void run(libraryApi.applySeries(id), t("已放好默认片头片尾"))}>
                {t("用默认片头片尾")}
              </button>
              <button type="button" className="btn btn-outline" onClick={() => void run(libraryApi.dismissSeries(id))}>
                {t("这一集不用")}
              </button>
            </div>
          )}
          <section className="card music-whole" data-tour="music-final">
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
            {/* no browser controls: the row below is the player (batch 7, B8) */}
            <audio
              ref={mixRef}
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
              onLoadedMetadata={applyRate}
              onTimeUpdate={(e) => setNow(e.currentTarget.currentTime)}
              onSeeked={(e) => setNow(e.currentTarget.currentTime)}
            />
            <div className="row gap8 wrap mix-controls">
              <button
                type="button"
                className="btn btn-small btn-primary mix-play"
                onClick={() => {
                  const a = mixRef.current;
                  if (a) void (a.paused ? a.play().catch(() => undefined) : a.pause());
                }}
                aria-label={playing ? t("暂停") : t("播放")}
                data-testid="mix-play"
              >
                {playing ? "❚❚" : "▶"}
              </button>
              <button type="button" className="btn btn-small btn-outline" onClick={() => skip(-SKIP_S)} aria-label={t("后退 5 秒")}>
                {t("−5 秒")}
              </button>
              <button type="button" className="btn btn-small btn-outline" onClick={() => skip(SKIP_S)} aria-label={t("前进 5 秒")}>
                {t("+5 秒")}
              </button>
              <SpeedButton rate={speed.rate} onChange={speed.setRate} testId="mix-speed" hint={t("播放速度（点一下切换）")} />
              <span className="mono small muted" data-testid="mix-clock">
                {fmt(now)} / {fmt(m.duration)}
              </span>
            </div>
          </section>
          <audio ref={clipRef} onEnded={() => setPreview(null)} data-testid="placement-audio" />
          <ul className="music-list">
            {m.placements.map((p) => (
              <PlacementCard
                key={`${p.id}:${p.role}`} // a new type has other fields: start the card afresh
                p={p}
                open={sel === p.id}
                more={more}
                onOpen={() => setSel(sel === p.id ? null : p.id)}
                onMore={setMore}
                taken={m.placements.filter((x) => x.id !== p.id).map((x) => x.role)}
                previewing={playing && preview === p.id}
                onPreview={() => listen(p)}
                onSave={(patch, done) => run(libraryApi.updatePlacement(id, p.id, patch), done ?? t("已保存"))}
                onRemove={() => void run(libraryApi.removePlacement(id, p.id), t("已去掉{role_label}", { role_label: p.role_label }))}
              />
            ))}
          </ul>
          {!empty && (
            <>
              {m.placements.length === 0 && <p className="muted">{t("这一集还没有配乐。左边点「放到」，或者「按用途自动放好」。")}</p>}
              <div data-tour="music-assist">
                <MusicChatBox onSend={(text) => run(libraryApi.musicChat(id, text))} />
              </div>
            </>
          )}
          <div className="card" data-tour="music-credits">
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
        </div>
      </div>
    </main>
  );
}
