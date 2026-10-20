import { useCallback, useEffect, useRef, useState } from "react";
import type { EpisodeListItem, ImportJob } from "../../api";
import { api, fmt } from "../../api";
import { t } from "../../i18n";
import { JobProgress } from "../loading/Loading";
import type { JobStep } from "../loading/Loading";
import { importApi, uploadTrack, type ImportJobView, type PickedTrack } from "./api";
import { hostList, LANGUAGE_LABELS, LANGUAGES, useShow, type Host, type Language, type Show } from "../show/api";
import "./import.css";

const RUNNING = new Set(["queued", "running"]);
const STATE_LABEL: Record<ImportJob["state"], string> = {
  queued: t("排队中"),
  running: t("导入中"),
  done: t("已完成"),
  error: t("出错了"),
  interrupted: t("中断了"),
  cancelled: t("已取消"),
};

const LEGACY_HOSTS: [string, string][] = [
  ["L", "Leon"],
  ["P", "Pei"],
];

/** The importer's steps and their share of the progress (lacuna_app/importer.py steps_of): one ASR step per track. */
function steps(j: ImportJob): [string, number, string][] {
  const hosts = j.hosts?.length ? j.hosts : LEGACY_HOSTS;
  return [
    ["models", 0.04, t("准备识别模型")],
    ...hosts.map(([tag, name]): [string, number, string] => [`asr_${tag}`, 0.68 / hosts.length, t("识别 {name} 的分轨", { name })]),
    ["features", 0.04, t("分析停顿、语速和重叠")],
    ["first_cut", 0.2, t("AI 第一刀")],
    ["episode", 0.04, t("生成审阅")],
  ];
}

// the same formats as the media library's drop zone (lacuna_app/importer.py AUDIO_EXT)
const ACCEPT = ".wav,.flac,.aif,.aiff,.mp3,.m4a,.ogg,.opus,.aac,audio/*";

function jobSteps(j: ImportJob): JobStep[] {
  let before = 0;
  return steps(j).map(([key, w, label]) => {
    const from = before;
    before += w;
    if (j.steps?.[key]) return { label, state: "done" };
    if (j.step === key) return { label, state: "now", progress: Math.min(Math.max((j.progress - from) / w, 0), 1) };
    return { label, state: "todo" };
  });
}

/** When the work started, counting earlier runs of a resumed import (elapsed_s) as time already used. */
function startedAt(j: ImportJob): number | undefined {
  return j.run_started ? Date.parse(j.run_started) - (j.elapsed_s ?? 0) * 1000 : undefined;
}

/** A host's track slot, by the host's tag (lacuna_app/show.py). */
type Who = string;
/** One track slot: a file being copied to the app, or one it has. */
interface Slot {
  key: object;
  name: string;
  progress: number;
  track?: PickedTrack;
  error?: string;
  abort?: () => void;
}

const hasFiles = (e: DragEvent | React.DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes("Files");

/** Which slot each dropped file belongs to: by a host's name in the file name ("Leon.wav"), else the
 *  free slots in order. `hosts`: [tag, name] of every slot. */
export function assign(files: File[], free: Who[], hosts: Host[]): [Who, File][] {
  const out = new Map<Who, File>();
  const rest: File[] = [];
  // longer names first, so "Anna" wins over "Ann" in "anna.wav"
  const byName = [...hosts].filter((h) => h.name.trim().length >= 2).sort((a, b) => b.name.length - a.name.length);
  for (const f of files) {
    const n = f.name.toLowerCase();
    const who = byName.find((h) => n.includes(h.name.trim().toLowerCase()) && !out.has(h.tag))?.tag;
    if (who) out.set(who, f);
    else rest.push(f);
  }
  const order = [...free, ...hosts.map((h) => h.tag).filter((w) => !free.includes(w))];
  for (const f of rest) {
    const who = order.find((w) => !out.has(w));
    if (who) out.set(who, f);
  }
  return [...out];
}

function NewImport({
  nextId,
  hosts,
  showLanguage,
  dropped,
  albums,
  album: albumAtStart,
  onStarted,
  onCancel,
}: {
  nextId: string;
  albums: { id: string; name: string }[];
  album: string;
  hosts: Host[];
  showLanguage: Language;
  dropped: File[] | null;
  onStarted: () => void;
  onCancel: () => void;
}) {
  const [id, setId] = useState(nextId);
  const [title, setTitle] = useState("");
  const [language, setLanguage] = useState<Language>(showLanguage);
  const [album, setAlbum] = useState(albumAtStart);
  const [slots, setSlots] = useState<Record<Who, Slot | null>>(() => Object.fromEntries(hosts.map((h) => [h.tag, null])));
  const [over, setOver] = useState<Who | "all" | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const live = useRef(slots);
  live.current = slots;
  const started = useRef(false);
  const inputs = useRef<Record<string, HTMLInputElement | null>>({});
  const many = hosts.length > 1;
  const names = hostList({ hosts } as Show);

  const letGo = (s: Slot | null) => {
    s?.abort?.();
    if (s?.track) void importApi.removeTrack(s.track.path).catch(() => undefined);
  };
  // leaving the form without importing: the app drops the copies it made
  useEffect(
    () => () => {
      if (!started.current) Object.values(live.current).forEach(letGo);
    },
    [],
  );

  const put = (who: Who, file: File) => {
    letGo(live.current[who]);
    const key = {}; // this upload, so a late answer for a replaced file is ignored
    const mine = (s: Record<Who, Slot | null>) => s[who]?.key === key;
    const up = uploadTrack(file, (p) => setSlots((s) => (mine(s) && !s[who]!.track ? { ...s, [who]: { ...s[who]!, progress: p } } : s)));
    setSlots((s) => ({ ...s, [who]: { key, name: file.name, progress: 0, abort: up.abort } }));
    up.done
      .then((track) => {
        if (!mine(live.current)) void importApi.removeTrack(track.path).catch(() => undefined);
        setSlots((s) => (mine(s) ? { ...s, [who]: { key, name: file.name, progress: 1, track } } : s));
      })
      .catch((e: Error) => {
        if (e.name !== "AbortError") setSlots((s) => (mine(s) ? { ...s, [who]: { key, name: file.name, progress: 0, error: e.message } } : s));
      });
  };
  const add = (files: File[], only?: Who) => {
    setErr(null);
    if (only) {
      if (files[0]) put(only, files[0]);
      return;
    }
    const free = hosts.map((h) => h.tag).filter((w) => !live.current[w]);
    for (const [who, f] of assign(files.slice(0, hosts.length), free, hosts)) put(who, f);
  };
  useEffect(() => {
    if (dropped?.length) add(dropped);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dropped]);

  const paths = hosts.map((h) => slots[h.tag]?.track?.path ?? "");
  const copying = Object.values(slots).some((s) => s && !s.track && !s.error);
  const start = async () => {
    setBusy(true);
    setErr(null);
    try {
      await api.startImport({ id: id.trim(), title: title.trim(), tracks: paths, language, ...(album ? { album } : {}) });
      started.current = true;
      onStarted();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const dropProps = (who: Who | "all") => ({
    onDragOver: (e: React.DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      e.stopPropagation();
      e.dataTransfer.dropEffect = "copy";
      setOver(who);
    },
    onDragLeave: (e: React.DragEvent) => {
      if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOver((o) => (o === who ? null : o));
    },
    onDrop: (e: React.DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      e.stopPropagation();
      setOver(null);
      const files = Array.from(e.dataTransfer.files);
      if (files.length) add(files, who === "all" ? undefined : who);
    },
  });
  const nameOf = (who: Who) => hosts.find((h) => h.tag === who)?.name ?? who;
  const tid = (who: Who) => (who === "all" ? "all" : nameOf(who).toLowerCase()); // test ids: import-slot-leon …
  const fileInput = (who: Who | "all") => (
    <input
      ref={(el) => {
        inputs.current[who] = el;
      }}
      type="file"
      multiple={who === "all"}
      accept={ACCEPT}
      hidden
      data-testid={`import-file-${tid(who)}`}
      aria-label={
        who === "all"
          ? many
            ? t("选择 {n} 条分轨", { n: hosts.length })
            : t("选择分轨")
          : t("选择 {name} 的分轨", { name: nameOf(who) })
      }
      onChange={(e) => {
        const files = Array.from(e.target.files ?? []);
        e.target.value = "";
        if (files.length) add(files, who === "all" ? undefined : who);
      }}
    />
  );
  return (
    <section className="card import-new" aria-label={t("导入新一集")} {...dropProps("all")}>
      <div className="card-head">
        <h2>{t("导入新一集")}</h2>
      </div>
      <div className="import-grid">
        <label>
          {t("剧集编号")}
          <input value={id} onChange={(e) => setId(e.target.value)} data-testid="import-id" />
        </label>
        <label>
          {t("标题（可不填）")}
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder={`${id} · …`} data-testid="import-title" />
        </label>
        <label>
          {t("这一集说的语言")}
          <select value={language} onChange={(e) => setLanguage(e.target.value as Language)} data-testid="import-language">
            {LANGUAGES.map((l) => (
              <option key={l} value={l}>
                {LANGUAGE_LABELS[l]}
              </option>
            ))}
          </select>
        </label>
        {albums.length > 0 && (
          <label>
            {t("放进专辑")}
            <select value={album} onChange={(e) => setAlbum(e.target.value)} data-testid="import-album">
              <option value="">{t("不放进专辑")}</option>
              {albums.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      <div className={`lib-drop import-drop${over === "all" ? " lib-drop-active" : ""}`} data-testid="import-drop">
        <p className="lib-drop-title">{t("把 {names} 的分轨拖到这里", { names })}</p>
        <div className="row gap12 lib-drop-actions">
          <button type="button" className="btn btn-primary" onClick={() => inputs.current.all?.click()}>
            {t("选择文件")}
          </button>
        </div>
        {many && (
          <p className="small muted">
            {t("可以一次拖 {n} 个。文件名里有主持人名字的会自动对上，也可以拖到下面某一条上。", { n: hosts.length })}
          </p>
        )}
        {fileInput("all")}
      </div>
      <div className="import-slots">
        {hosts.map((h, i) => {
          const k = h.tag;
          const s = slots[k];
          return (
            <div
              key={k}
              className={`import-slot${over === k ? " import-slot-over" : ""}${s?.track ? " import-slot-set" : ""}`}
              data-testid={`import-slot-${tid(k)}`}
              {...dropProps(k)}
            >
              <span className={`dot host-dot-${i}`} aria-hidden />
              <strong>{t("{name} 的分轨", { name: h.name })}</strong>
              <span className="import-slot-file small" title={s?.track?.path ?? s?.name}>
                {!s ? (
                  <span className="muted" data-testid={`import-${tid(k)}`}>
                    {t("还没选")}
                  </span>
                ) : s.error ? (
                  <span className="error" data-testid={`import-${tid(k)}`}>
                    {s.name}：{s.error}
                  </span>
                ) : s.track ? (
                  <>
                    <span data-testid={`import-${tid(k)}`}>{s.track.name}</span>
                    <span className="muted">
                      {s.track.duration != null ? ` · ${fmt(s.track.duration)}` : ""} · {(s.track.size / 1e6).toFixed(0)} MB
                    </span>
                  </>
                ) : (
                  <span data-testid={`import-${tid(k)}`} className="import-slot-copying">
                    <span>{t("正在读入 {name} · {pct}%", { name: s.name, pct: Math.round(s.progress * 100) })}</span>
                    <span className="import-slot-bar" aria-hidden>
                      <span style={{ width: `${Math.max(s.progress * 100, 2)}%` }} />
                    </span>
                  </span>
                )}
              </span>
              <button type="button" className="btn btn-small btn-outline" onClick={() => inputs.current[k]?.click()}>
                {s ? t("换一个") : t("选择文件")}
              </button>
              {fileInput(k)}
            </div>
          );
        })}
        {hosts.length === 2 && slots[hosts[0].tag] && slots[hosts[1].tag] && (
          <button
            type="button"
            className="btn btn-small btn-ghost import-swap"
            onClick={() => setSlots((s) => ({ [hosts[0].tag]: s[hosts[1].tag], [hosts[1].tag]: s[hosts[0].tag] }))}
            data-testid="import-swap"
          >
            {t("⇅ 对调 {a} 和 {b}", { a: hosts[0].name, b: hosts[1].name })}
          </button>
        )}
      </div>
      <p className="muted small">
        {t("原始录音只读，不会被改动。逐字识别和分析都在这台电脑上做，只有文字和数字会发给 LACUNA 的 AI 做第一刀。长录音要跑一阵，可以关掉这页，进度不会丢。")}
      </p>
      {err && <p className="error small">{err}</p>}
      <div className="row gap8">
        <button type="button" className="btn btn-primary" disabled={paths.some((p) => !p) || !id.trim() || busy || copying} onClick={() => void start()}>
          {t("开始导入")}
        </button>
        <button type="button" className="btn" onClick={onCancel}>
          {t("取消")}
        </button>
      </div>
    </section>
  );
}

function JobRow({ j, toReview, onChange }: { j: ImportJobView; toReview: number; onChange: () => void }) {
  const [err, setErr] = useState<string | null>(null);
  const act = (p: Promise<unknown>) => p.then(onChange).catch((e) => setErr((e as Error).message));
  const running = RUNNING.has(j.state);
  // the track files in host order; tags are the show's own (older imports: L + P)
  const trackFiles = (j.hosts?.map(([tag]) => tag) ?? ["L", "P"]).map((tag) => j.tracks[tag]).filter(Boolean);
  return (
    <li className={`job job-${j.state}`} data-testid="import-job" data-state={j.state}>
      <div className="row gap8 wrap">
        <strong>{j.title}</strong>
        {!running && <span className={`chip ${j.state === "done" ? "chip-ok" : ""}`}>{STATE_LABEL[j.state]}</span>}
        <span className="muted small">
          {trackFiles.map((x) => x.name).join(" + ")}
          {trackFiles[0]?.duration ? ` · ${fmt(trackFiles[0].duration)}` : ""}
        </span>
      </div>
      {running && (
        <JobProgress
          flat
          title={j.state === "queued" ? t("排队中，马上开始") : t("正在导入")}
          stage={j.stage}
          progress={j.progress}
          steps={jobSteps(j)}
          started={startedAt(j)}
          left={j.state === "running" ? (j.eta_s ?? null) : undefined}
          testId="import-progress"
          stepTestId="import-stage"
        />
      )}
      {j.state === "done" && j.result && (
        <p className="small">
          {j.result.engine === "rules"
            ? t("AI 第一刀（没连上 AI，只收紧了停顿）：{edits} 处改动，{review} 处需要你过目。", { edits: j.result.edits, review: toReview })
            : t("AI 第一刀：{edits} 处改动，{review} 处需要你过目。", { edits: j.result.edits, review: toReview })}
        </p>
      )}
      {j.error && j.state !== "done" && <p className="error small">{j.error}</p>}
      {err && <p className="error small">{err}</p>}
      <div className="row gap8">
        {j.state === "done" && (
          <a className="btn btn-primary btn-small linkbtn" href={`#/ep/${encodeURIComponent(j.id)}/review`}>
            {t("开始审阅")}
          </a>
        )}
        {running && (
          <button type="button" className="btn btn-small" onClick={() => void act(api.cancelImport(j.id))}>
            {t("取消")}
          </button>
        )}
        {["error", "interrupted", "cancelled"].includes(j.state) && (
          <button type="button" className="btn btn-small btn-outline-accent" onClick={() => void act(api.resumeImport(j.id))}>
            {t("继续")}
          </button>
        )}
        {!running && (
          <button type="button" className="btn btn-small" onClick={() => void act(api.forgetImport(j.id))}>
            {t("从列表移除")}
          </button>
        )}
      </div>
    </li>
  );
}

/**
 * Import form + task panel. Polls while a job runs; a job finishing here opens its review.
 * Audio files dragged anywhere onto the 剧集 page open the form with them (like the media library).
 */
export function ImportPanel({
  episodes,
  onEpisodesChanged,
  onOpen,
  albums = [],
  album = "",
}: {
  /** the 剧集 list, for each finished import's review progress */
  episodes: EpisodeListItem[] | null;
  /** the project's albums: the form offers to put the new episode in one (`album`: picked at first) */
  albums?: { id: string; name: string }[];
  album?: string;
  onEpisodesChanged: () => void;
  onOpen: (id: string) => void;
}) {
  const [jobs, setJobs] = useState<ImportJobView[] | null>(null);
  const [nextId, setNextId] = useState("EP001");
  const [form, setForm] = useState(false);
  const [dropped, setDropped] = useState<File[] | null>(null);
  const prev = useRef<Map<string, string>>(new Map());
  const show = useShow();
  const hosts = show?.hosts ?? [];

  const refresh = useCallback(async () => {
    try {
      const r = await importApi.imports();
      setJobs(r.jobs);
      setNextId(r.next_id);
      const seen = prev.current;
      for (const j of r.jobs) {
        if (j.state === "done" && seen.has(j.id) && RUNNING.has(seen.get(j.id)!)) {
          onEpisodesChanged();
          onOpen(j.id); // finished while Leon is looking: straight into review
        }
      }
      prev.current = new Map(r.jobs.map((j) => [j.id, j.state]));
    } catch {
      /* server restarting: try again on the next tick */
    }
  }, [onEpisodesChanged, onOpen]);

  const active = jobs?.some((j) => RUNNING.has(j.state)) ?? false;
  // a finished import follows its episode's review: the count left to look at, and once all of it is
  // looked at the episode card says so and the task card goes (验收 V3)
  const pending = (j: ImportJobView) => episodes?.find((e) => e.id === j.id)?.pending_review ?? j.result?.to_review ?? 0;
  const shown = jobs?.filter((j) => !(j.state === "done" && episodes?.find((e) => e.id === j.id)?.pending_review === 0)) ?? [];
  useEffect(() => {
    void refresh();
  }, [refresh]);
  useEffect(() => {
    if (!active) return;
    const t = window.setInterval(() => void refresh(), 1500);
    return () => window.clearInterval(t);
  }, [active, refresh]);

  // files dropped anywhere else on the page (the form's own areas handle theirs); while an import
  // runs a drop is ignored - never the browser's default, which would open the file in this tab
  useEffect(() => {
    const over = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
    };
    const drop = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      const files = Array.from(e.dataTransfer?.files ?? []);
      if (!files.length || active) return;
      setForm(true);
      setDropped(files);
    };
    window.addEventListener("dragover", over);
    window.addEventListener("drop", drop);
    return () => {
      window.removeEventListener("dragover", over);
      window.removeEventListener("drop", drop);
    };
  }, [active]);

  return (
    <div className="imports">
      {!form && (
        <button type="button" className="btn btn-primary" onClick={() => setForm(true)} disabled={active}>
          {t("导入新一集")}
        </button>
      )}
      {form && hosts.length > 0 && (
        <NewImport
          nextId={nextId}
          hosts={hosts}
          showLanguage={show?.language ?? "zh"}
          dropped={dropped}
          albums={albums}
          album={album}
          onCancel={() => {
            setForm(false);
            setDropped(null);
          }}
          onStarted={() => {
            setForm(false);
            setDropped(null);
            void refresh();
          }}
        />
      )}
      {!!shown.length && (
        <section aria-label={t("导入任务")}>
          <h2 className="sub">{t("导入任务")}</h2>
          <ul className="jobs">
            {shown.map((j) => (
              <JobRow key={j.id} j={j} toReview={pending(j)} onChange={() => void refresh()} />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
