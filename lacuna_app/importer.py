"""New-episode import: one raw track per host -> ASR -> features -> AI first cut -> reviewable episode.

One job at a time (CPU bound). Every finished step is written to ``<workspace>/imports/<id>/``
(ASR per track, tokens/features/editor document, each AI window), so a failed or interrupted
import resumes where it stopped instead of starting over. The raw tracks are only read; the new
episode references them by absolute path like every other episode (D29, read-only originals).

The hosts (one track each, in the order of 节目设置) come from the workspace's show (show.py) when the
import starts and are kept in the job, so a later rename doesn't change a running or resumed import.
So is the episode's language (the show's, unless the import form picked another): it decides the
speech recognisers (asr.ENGINES), the editor document's format notes and the AI editing brief.
Steps and their share of the progress bar: models 4 % (first import only), ASR 68 % split evenly over
the tracks, features 4 %, AI first cut 20 %, building the episode 4 %.
"""
from __future__ import annotations

import contextvars
import json
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

import soundfile as sf

from lacuna_core.media import MediaRef, conform

from . import asr as asr_mod
from . import import_eta
from . import import_queue
from . import learning
from . import show as show_mod
from .ai_cut import TrackTokens, build_episode, report_dict
from .archive import free_deleted_ids
from .episode import create_episode
from .events import track
from .store import PathError, Workspace, atomic_write_json, check_id, inside, read_json, now_iso as now
from .i18n import N_, tr

AUDIO_EXT = {".wav", ".flac", ".aif", ".aiff", ".mp3", ".m4a", ".ogg", ".opus", ".aac"}
LEGACY_HOSTS = (("L", "Leon"), ("P", "Pei"))      # jobs from before the show profile
JOB_FILE = "job.json"
ASR_SHARE = 0.68
STEP_LABELS = {"models": N_("准备识别模型"), "features": N_("分析停顿、语速和重叠"), "first_cut": N_("LACUNA 初剪"),
               "episode": N_("生成审阅")}


def job_hosts(job: dict) -> list[tuple[str, str]]:
    """[(tag, name)] of an import's tracks, in order."""
    return [(t, n) for t, n in (job.get("hosts") or LEGACY_HOSTS)]


def steps_of(job: dict) -> list[tuple[str, float]]:
    """(step, share of the progress bar) in order; one ASR step per track (``asr_<tag>``)."""
    hosts = job_hosts(job)
    return ([("models", 0.04)] + [(f"asr_{t}", ASR_SHARE / len(hosts)) for t, _ in hosts]
            + [("features", 0.04), ("first_cut", 0.20), ("episode", 0.04)])


def step_label(job: dict, step: str | None) -> str:
    names = dict(job_hosts(job))
    if step and step.startswith("asr_") and step[4:] in names:
        return tr("识别 {name} 的分轨", name=names[step[4:]])
    return tr(STEP_LABELS.get(step or "", N_("导入")))


STEPS = tuple(steps_of({}))       # a two-host import (import_eta's defaults)


class ImportBusy(RuntimeError):
    pass


class Cancelled(Exception):
    pass


class ImportError_(RuntimeError):
    """A problem the user can act on (message is Chinese)."""


def check_track(path: str | Path) -> dict:
    """Basic facts about a raw track, or a Chinese error."""
    p = Path(path).expanduser()
    if not p.is_file():
        raise ImportError_(tr("找不到文件：{p}", p=p))
    if p.suffix.lower() not in AUDIO_EXT:
        raise ImportError_(tr("不是音频文件：{name}", name=p.name))
    try:
        info = sf.info(str(p))
        return {"path": str(p.resolve()), "name": p.name, "duration": round(info.frames / info.samplerate, 2),
                "sample_rate": info.samplerate, "channels": info.channels, "size": p.stat().st_size}
    except Exception:      # noqa: BLE001 - libsndfile can't read it; ffmpeg will conform it later
        return {"path": str(p.resolve()), "name": p.name, "duration": None, "sample_rate": None,
                "channels": None, "size": p.stat().st_size}


class Importer:
    def __init__(self, ws: Workspace, first_cut_factory: Callable[[], Any] | None = None,
                 asr_backend: Any = None, models_dir: Path | None = None, gate: import_queue.Gate | None = None):
        from .first_cut import make_first_cut
        self.ws = ws
        self.root = ws.root / "imports"
        self.models_dir = Path(models_dir) if models_dir else ws.root / "models"
        self.first_cut_factory = first_cut_factory or (lambda: make_first_cut("auto"))
        self.asr_backend = asr_backend          # None = real sherpa-onnx ASR (tests inject a fake)
        # English: listens again to short sounds without words (dropped um/uh); None = real recogniser
        # with the real ASR, nothing with a fake one (tests inject a fake: audio -> [(tag, a, b)] -> [text])
        self.hear_backend: Callable[[dict], Callable] | None = None
        # proofreads the show's names in the recognised text (transcript_fix.py); None = the real one
        self.term_fixer: Any = None
        self._lock = threading.Lock()
        self._usage_lock = threading.Lock()
        self._gate = gate                       # None = the server's one queue (import_queue.GATE)
        # called with (episode id, job) when an import finishes: counts its audio hours (quota.py)
        self.on_done: Callable[[str, dict], None] | None = None
        # called with (episode id, tracks) before an import starts or resumes; raises ImportError_ when the
        # show's account has no audio hours left this month (quota.py)
        self.allow: Callable[[str, dict], None] | None = None
        # whether the AI first cut goes through the Batch API (half price, slower; ai_settings.py)
        self.batch_on: Callable[[], bool] | None = None
        self._cancel: set[str] = set()
        self.jobs: dict[str, dict] = {}
        self._history: dict | None = None      # past imports' step times (import_eta.py), read lazily
        self._load()

    # ------------------------------------------------------------------ persistence
    def dir_for(self, episode_id: str) -> Path:
        return inside(self.root, check_id(episode_id))

    def _load(self) -> None:
        if not self.root.is_dir():
            return
        for d in sorted(self.root.iterdir()):
            f = d / JOB_FILE
            if not f.is_file():
                continue
            try:
                job = read_json(f)
            except (OSError, ValueError):
                continue
            if job.get("hidden"):
                continue
            if job.get("state") in ("queued", "running"):
                job.update(state="interrupted", error=tr("导入中途停了，点「继续」从断点接着做。"))
            self.jobs[job["id"]] = job

    def _save(self, job: dict) -> None:
        d = self.dir_for(job["id"])
        d.mkdir(parents=True, exist_ok=True)
        atomic_write_json(d / JOB_FILE, job)

    def status(self, episode_id: str | None = None):
        with self._lock:
            if episode_id is not None:
                j = self.jobs.get(episode_id)
                return self._view(j) if j else None
            return sorted((self._view(j) for j in self.jobs.values()), key=lambda j: j.get("created", ""), reverse=True)

    @property
    def gate(self) -> import_queue.Gate:
        return self._gate or import_queue.GATE

    def _key(self, episode_id: str) -> str:
        return f"{self.ws.root}::{episode_id}"

    @property
    def _running(self) -> str | None:
        """The import of this workspace that is running now (others may wait behind it)."""
        return next((j["id"] for j in list(self.jobs.values()) if j.get("state") == "running"), None)

    def active(self) -> list[str]:
        """Imports of this workspace that run or wait their turn."""
        return [j["id"] for j in list(self.jobs.values()) if j.get("state") in ("queued", "running")]

    def _view(self, job: dict) -> dict:
        out = dict(job)
        if job.get("state") == "queued":
            ahead = self.gate.ahead(self._key(job["id"]))
            out["ahead"] = ahead
            if ahead:
                out["stage"] = tr("排队中，前面还有 {n} 集", n=ahead)
        if job.get("state") == "running":
            if self._history is None:
                self._history = import_eta.history(self.root)
            out["eta_s"] = import_eta.estimate(job, self._history)
        return out

    def track_paths(self) -> list[str]:
        """Every raw track a listed import refers to (imported_tracks.py keeps those copies)."""
        with self._lock:
            return [t["path"] for j in self.jobs.values() for t in j.get("tracks", {}).values()]

    # ------------------------------------------------------------------ control
    def start(self, episode_id: str, title: str, paths: list[str], wait: bool = False,
              language: str | None = None) -> dict:
        """`paths`: one raw track per host of the workspace's show, in the order of 节目设置.
        `language`: what the hosts speak (asr.LANGUAGES); None = the show's language."""
        try:
            check_id(episode_id)
        except PathError:
            raise ImportError_(tr("剧集编号不能含 \\ / : * ? \" < > | 等字符"))
        if episode_id in self.ws.episode_ids():
            raise ImportError_(tr("已经有一集叫 {episode_id}，换个编号", episode_id=episode_id))
        free_deleted_ids(self.ws)     # a deleted episode's evidence must not become this one's
        profile = show_mod.load(self.ws.root)
        hosts = show_mod.tracks(profile)
        if language is not None and language not in asr_mod.LANGUAGES:
            raise ImportError_(tr("不支持这种语言：{language}", language=language))
        language = language or profile.get("language") or "zh"
        if not hosts:
            raise ImportError_(tr("先在「节目」里填好主持人"))
        if len(paths) > show_mod.MAX_HOSTS:
            raise ImportError_(tr("每个节目最多 {n} 位主持人，一集最多导入 {n} 条分轨，收到 {got} 条", n=show_mod.MAX_HOSTS, got=len(paths)))
        if len(paths) != len(hosts):
            raise ImportError_(tr("要 {n} 条分轨（每位主持人一条），收到 {got} 条", n=len(hosts), got=len(paths)))
        tracks = {tag: check_track(p) for (tag, _), p in zip(hosts, paths)}
        seen: dict[str, str] = {}
        for tag, name in hosts:
            other = seen.get(tracks[tag]["path"])
            if other:
                raise ImportError_(tr("{a} 和 {b} 选了同一个文件", a=other, b=name))
            seen[tracks[tag]["path"]] = name
        with self._lock:
            old = self.jobs.get(episode_id)
            if old and old["state"] in ("queued", "running"):
                raise ImportBusy(tr("这一集已经在导入"))
        if self.allow is not None:
            self.allow(episode_id, tracks)
        self._fresh_cache(episode_id, tracks)
        job = {"id": episode_id, "title": title.strip() or episode_id, "tracks": tracks,
               "hosts": [list(h) for h in hosts], "language": language,
               "state": "queued", "progress": 0.0, "step": None, "stage": tr("排队"), "steps": {},
               "created": now(), "started": None, "finished": None, "error": None, "result": None}
        return self._launch(job, wait)

    def _fresh_cache(self, episode_id: str, tracks: dict) -> None:
        """A new import under an id used before (a failed or removed one): the saved steps belong to the
        old tracks, so they go unless the tracks are the very same files."""
        d = self.dir_for(episode_id)
        if not d.is_dir():
            return
        try:
            before = {t: x.get("path") for t, x in (read_json(d / JOB_FILE).get("tracks") or {}).items()}
        except (OSError, ValueError):
            before = None
        if before == {t: x["path"] for t, x in tracks.items()}:
            return
        import shutil
        for p in d.iterdir():
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)

    def resume(self, episode_id: str, wait: bool = False) -> dict:
        with self._lock:
            job = self.jobs.get(episode_id)
        if job is None:
            raise KeyError(episode_id)
        if job["state"] not in ("error", "interrupted", "cancelled"):
            raise ImportBusy(tr("这一集不需要继续"))
        if self.allow is not None:
            self.allow(episode_id, job["tracks"])
        job = dict(job, state="queued", error=None, stage=tr("排队"))
        return self._launch(job, wait)

    def cancel(self, episode_id: str) -> None:
        with self._lock:
            if self.jobs.get(episode_id, {}).get("state") not in ("queued", "running"):
                raise KeyError(episode_id)
            self._cancel.add(episode_id)

    def forget(self, episode_id: str) -> None:
        """Remove a finished/failed job from the list (its cached files stay on disk)."""
        with self._lock:
            j = self.jobs.get(episode_id)
            if j is None:
                raise KeyError(episode_id)
            if j["state"] in ("queued", "running"):
                raise ImportBusy(tr("正在导入，先取消"))
            j["hidden"] = True
            self._save(j)
            del self.jobs[episode_id]

    def drop(self, episode_id: str) -> None:
        """Forget a job whose cache is being deleted with its episode (archive.py)."""
        with self._lock:
            if self.jobs.get(episode_id, {}).get("state") not in ("queued", "running"):
                self.jobs.pop(episode_id, None)

    def _launch(self, job: dict, wait: bool) -> dict:
        with self._lock:
            self._cancel.discard(job["id"])
            self.jobs[job["id"]] = job
        self._save(job)
        if wait:
            self._run(job)
        else:
            # the worker keeps the request's context: whose learned rules and 剪辑力度 apply (habits.py)
            run = contextvars.copy_context().run
            threading.Thread(target=run, args=(self._run, job), name=f"import-{job['id']}", daemon=True).start()
        return dict(job)

    # ------------------------------------------------------------------ the job
    def _progress(self, job: dict, step: str, frac: float, stage: str) -> None:
        if job["id"] in self._cancel:
            raise Cancelled()
        steps = steps_of(job)
        before = sum(w for s, w in steps[:[s for s, _ in steps].index(step)])
        weight = dict(steps)[step]
        with self._lock:
            if job.get("step") != step:          # when each step started, for the time-left estimate
                job.update(step_at=time.time(), step_first=None)
            elif frac > 0 and not job.get("step_first"):
                job["step_first"] = [round(time.time() - job["step_at"], 1), round(frac, 4)]
            job["step"] = step
            job["stage"] = stage
            job["progress"] = round(min(before + weight * min(max(frac, 0.0), 1.0), 0.999), 4)

    def _done_step(self, job: dict, step: str, info: dict | None = None) -> None:
        with self._lock:
            job["steps"][step] = {"done": now(), **(info or {})}
            if job.get("step") == step and job.get("step_at"):
                job["steps"][step].setdefault("seconds", round(time.time() - job["step_at"], 1))
        self._save(job)

    def _run(self, job: dict) -> None:
        d = self.dir_for(job["id"])
        key = self._key(job["id"])
        try:
            self.gate.enter(key, lambda: job["id"] in self._cancel)
        except import_queue.Abandoned:
            with self._lock:
                job.update(state="cancelled", stage=tr("已取消"), error=tr("已取消。点「继续」从断点接着做。"), finished=now())
                self._cancel.discard(job["id"])
            self._save(job)
            return
        with self._lock:
            job.update(state="running", started=job.get("started") or now(), run_started=now())
        self._save(job)
        t0 = time.monotonic()
        try:
            self._steps(job, d)
            with self._lock:
                job.update(state="done", progress=1.0, stage=tr("完成，可以开始审阅"), finished=now())
        except Cancelled:
            with self._lock:
                job.update(state="cancelled", stage=tr("已取消"), error=tr("已取消。点「继续」从断点接着做。"), finished=now())
        except ImportError_ as e:
            with self._lock:
                job.update(state="error", error=str(e), finished=now())
        except Exception as e:     # noqa: BLE001 - surfaced to the UI; full trace on the console
            traceback.print_exc()
            with self._lock:
                job.update(state="error", error=tr("{p0}出错：{p1}", p0=step_label(job, job.get("step")), p1=e or type(e).__name__),
                           finished=now())
        finally:
            self.gate.leave(key)
            with self._lock:
                job["elapsed_s"] = round(job.get("elapsed_s", 0) + time.monotonic() - t0, 1)
                self._cancel.discard(job["id"])
                self._history = None             # this run's step times count from now on
            self._save(job)
            audio = max((t.get("duration") or 0 for t in job["tracks"].values()), default=0)
            track(f"import.{job['state']}", job["id"], audio_s=round(audio, 1), seconds=job["elapsed_s"],
                  tracks=len(job["tracks"]), language=job.get("language") or "zh",
                  edits=(job.get("result") or {}).get("edits"), to_review=(job.get("result") or {}).get("to_review"),
                  failed_step=job.get("step") if job["state"] == "error" else None)
            if job["state"] == "done" and self.on_done is not None:
                try:
                    self.on_done(job["id"], dict(job))
                except Exception:      # noqa: BLE001 - the episode is made; a metering failure must not undo that
                    traceback.print_exc()

    def _steps(self, job: dict, d: Path) -> None:
        backend = self.asr_backend
        lang = asr_mod.language(job.get("language"))
        # 1. models (real ASR only)
        if backend is None:
            if not asr_mod.sherpa_installed():
                raise ImportError_(tr("没装语音识别组件 sherpa-onnx（pip install -e \".[asr]\"）"))
            if not asr_mod.models_present(self.models_dir, lang):
                asr_mod.ensure_models(self.models_dir, lambda f, s: self._progress(job, "models", f, s), lang=lang)
        self._done_step(job, "models")

        # 2. ASR per track (cached)
        rec = None
        audio16: dict[str, Any] = {}
        asr: dict[str, dict] = {}
        hosts = job_hosts(job)
        todo = [tag for tag, _ in hosts if not (d / f"asr_{tag}.json").is_file()]
        # the next track is decoded (ffmpeg, ~10 s an hour) while this one is being recognised
        prefetch = ThreadPoolExecutor(1, thread_name_prefix="decode16k")
        decoded = {tag: prefetch.submit(asr_mod.decode_16k, job["tracks"][tag]["path"]) for tag in todo[:1]}
        try:
            for tag, name in hosts:
                step = f"asr_{tag}"
                out = d / f"asr_{tag}.json"
                if out.is_file():
                    asr[tag] = read_json(out)
                    continue
                self._progress(job, step, 0.0, tr("解码 {name} 的分轨", name=name))
                t = time.monotonic()
                x = decoded.pop(tag).result()
                audio16[tag] = x
                for nxt in todo[todo.index(tag) + 1:][:1]:
                    decoded[nxt] = prefetch.submit(asr_mod.decode_16k, job["tracks"][nxt]["path"])
                if backend is None:
                    if rec is None:
                        self._progress(job, step, 0.01, tr("加载识别模型"))
                        rec = asr_mod.load_recognizers(self.models_dir, lang=lang)
                    res = asr_mod.transcribe(x, rec, lambda f, s, step=step, name=name:
                                             self._progress(job, step, f, f"{name}：{s}"))
                else:
                    res = backend(tag, x, lambda f, s, step=step, name=name: self._progress(job, step, f, f"{name}：{s}"))
                atomic_write_json(out, res)
                asr[tag] = res
                self._done_step(job, step, {"seconds": round(time.monotonic() - t, 1),
                                            "segments": len(res["segments"]), "audio_s": res["audio_s"]})
        finally:
            for f in decoded.values():
                f.cancel()
            prefetch.shutdown(wait=False)     # a cancelled import does not wait for a decode it no longer needs
        rec = None

        # 3. features + editor document (cached)
        from . import features
        tok_p, feat_p, doc_p = d / "tokens.json", d / "features.json", d / "editor_input.md"
        if not (tok_p.is_file() and feat_p.is_file() and doc_p.is_file()):
            self._progress(job, "features", 0.0, tr("分析停顿、语速和重叠"))
            for tag, _ in hosts:
                if tag not in audio16:
                    audio16[tag] = asr_mod.decode_16k(job["tracks"][tag]["path"])
            profile = show_mod.load(self.ws.root)
            self._fix_terms(job, d, asr, hosts)
            hear = None
            if lang == "en":
                if self.hear_backend is not None:
                    hear = self.hear_backend(audio16)
                elif backend is None:
                    self._progress(job, "features", 0.3, tr("找识别漏掉的 um / uh"))
                    hear = asr_mod.Listener(asr_mod.load_main(self.models_dir, lang), audio16)
            tokens_doc, feats, doc = features.build(asr, audio16, job["id"], log=lambda *_: None, names=dict(hosts),
                                                    show_name=profile["show_name"], lang=lang, hear=hear)
            hear = None
            atomic_write_json(feat_p, feats)
            atomic_write_json(tok_p, tokens_doc)
            doc_p.write_text(doc, encoding="utf-8")
            self._done_step(job, "features", {"tokens": {t: len(v) for t, v in tokens_doc["tracks"].items()},
                                              "fillers": feats["stats"].get("filler_candidates", 0)})
        audio16.clear()
        self.gate.leave(self._key(job["id"]))      # the AI first cut waits on the network: the next import may start
        tokens_doc = read_json(tok_p)
        tokens = {tag: TrackTokens(t) for tag, t in tokens_doc["tracks"].items()}
        doc = doc_p.read_text(encoding="utf-8")

        # 4. AI first cut (each window cached)
        ops_p = d / "ops.json"
        if ops_p.is_file():
            ops_doc = read_json(ops_p)
        else:
            fc = self.first_cut_factory()
            if hasattr(fc, "names"):              # whose track is whose (prompt, rule reasons)
                fc.names = dict(hosts)
            if hasattr(fc, "show"):
                fc.show = show_mod.load(self.ws.root)
            if hasattr(fc, "language"):
                fc.language = lang
            if hasattr(fc, "on_usage"):
                fc.on_usage = lambda u: self._log_usage(job["id"], u)     # logged per call, failures included
            if hasattr(fc, "batch"):
                fc.batch = bool(self.batch_on and self.batch_on())
            duration = max(a["audio_s"] for a in asr.values())
            extra = learning.prompt_rules(self.ws)      # rules Leon approved on 「学到的规则」 ("" if none)
            self._progress(job, "first_cut", 0.0, tr("LACUNA 初剪") if fc.name == "claude" else tr("规则初剪（AI 没接上）"))
            try:
                res = fc.run(doc, duration, tokens, job["id"],
                             progress=lambda f, s: self._progress(job, "first_cut", f, s),
                             cache_dir=d / "ai_windows", cancelled=lambda: job["id"] in self._cancel,
                             extra_rules=extra)
            except Exception as e:
                from .first_cut import FirstCutError
                if isinstance(e, FirstCutError):
                    if job["id"] in self._cancel:
                        raise Cancelled()
                    raise ImportError_(tr("LACUNA 初剪没做完：{e}。已剪好的段落都存着，点「继续」接着剪。", e=e))
                raise
            ops_doc = res.ops_doc
            atomic_write_json(ops_p, ops_doc)
            self._done_step(job, "first_cut", {"engine": fc.name, "ops": len(ops_doc["ops"]), "usage": res.usage})

        # 5. episode
        self._progress(job, "episode", 0.0, tr("生成审阅（核对音频）"))
        media = self._media(job, d)
        self._progress(job, "episode", 0.5, tr("生成审阅（精修剪辑点）"))
        project, edits, transcript, report = build_episode(media, ops_doc, tokens,
                                                           policy=learning.review_policy(self.ws), names=dict(hosts))
        if lang == "en":        # the um / uh the recognisers dropped become words (fillers.py)
            from . import fillers
            transcript = fillers.merge(transcript, read_json(feat_p).get("sounds", []), dict(hosts))
        engine = job["steps"].get("first_cut", {}).get("engine", "claude")
        meta = {"title": job["title"], "demo": False, "raw_offset_s": 0.0, "source": "import",
                "ai_model": ops_doc.get("model", ""), "ai_notes": ops_doc.get("notes", ""),
                "ai_report": report_dict(report), "first_cut_engine": engine,
                "imported_at": now(), "language": lang, "raw_tracks": {name: job["tracks"][tag]["path"] for tag, name in hosts}}
        create_episode(self.ws, job["id"], meta, project, edits, transcript)
        self._mark_checked(job, d)
        self._level(job["id"])          # not cancellable: the episode exists now
        self._default_music(job["id"])
        cons = sum(e.consequential for e in edits)
        dur = project.base.length / project.base.sample_rate
        with self._lock:
            job["result"] = {"episode": job["id"], "edits": len(edits), "to_review": cons,
                             "raw_duration": round(dur, 1),
                             "skipped": sum(report.skipped.values()), "engine": engine}
        self._done_step(job, "episode")

    def _fix_terms(self, job: dict, d: Path, asr: dict[str, dict], hosts: list[tuple[str, str]]) -> None:
        """The show's names mis-heard by the recognisers, fixed in `asr` in place (transcript_fix.py).
        The checked answer is kept in ``term_fixes.json`` so a resumed import asks only once."""
        from . import transcript_fix as tf
        p = d / "term_fixes.json"
        lines = tf.lines_from_asr(asr, dict(hosts))
        if p.is_file():          # a resumed import: what the model said, under today's rule (sounds alike)
            fixes = [f for f in read_json(p).get("fixes", []) if tf.sounds_alike(str(f.get("wrong", "")), str(f.get("right", "")))]
        else:
            self._progress(job, "features", 0.0, tr("按节目设置校对专有名词"))
            fixer = self.term_fixer if self.term_fixer is not None else tf.TranscriptFixer()
            g = tf.glossary_for(self.ws.root, job.get("title") or "", [name for _, name in hosts])
            fixes, complete = fixer.propose_all(lines, g, on_usage=lambda u: self._log_usage(job["id"], u))
            # sig: the glossary the model checked every line with (else the episode is checked again when it opens)
            atomic_write_json(p, {"fixes": fixes, "terms": g.terms, "sig": tf.signature(g) if complete else None})
        done = tf.apply(lines, fixes)
        tf.write_back(asr, lines, done)
        if done:
            self._done_step(job, "terms", {"fixes": tf.summary(done)})

    def _mark_checked(self, job: dict, d: Path) -> None:
        """The new episode's transcript was proofread with this glossary (no second pass when it opens)."""
        from .store import atomic_write_json as write
        try:
            sig = read_json(d / "term_fixes.json").get("sig")
        except (OSError, ValueError):
            sig = None
        if sig:
            from .transcript_fix import CHECK_VERSION
            write(self.ws.episode_dir(job["id"]) / "term_check.json", {"sig": sig, "v": CHECK_VERSION, "at": now()})

    def _media(self, job: dict, d: Path) -> dict[str, MediaRef]:
        """Raw tracks as MediaRefs (read in place); conformed to WAV only if they can't be."""
        refs: dict[str, MediaRef] = {}
        hosts = job_hosts(job)
        for tag, name in hosts:
            try:
                refs[name] = MediaRef.probe(job["tracks"][tag]["path"])
            except Exception:       # noqa: BLE001 - format libsndfile can't read
                refs[name] = None    # type: ignore[assignment]
        rates = {r.sample_rate for r in refs.values() if r is not None}
        if None in refs.values() or len(rates) > 1:
            sr = max(rates) if rates else 48000
            for tag, name in hosts:
                r = refs[name]
                if r is None or r.sample_rate != sr:
                    self._progress(job, "episode", 0.2, tr("把 {name} 的分轨转成 {sr} Hz WAV", name=name, sr=sr))
                    refs[name] = conform(job["tracks"][tag]["path"], d / "media" / f"{name}.wav", sr)
        return refs

    def _level(self, episode_id: str) -> None:
        """Even out the hosts' loudness from the start (backlog 7, levels.py); a failure only skips it."""
        from . import levels
        from .episode import Episode
        try:
            ep = Episode(self.ws, episode_id)
            try:
                levels.level_new_episode(ep)
            finally:
                ep.close()
        except Exception:      # noqa: BLE001 - the episode is usable without it; 「声音」 can level it later
            traceback.print_exc()

    def _default_music(self, episode_id: str) -> None:
        """The album's (else the project's) opener and ending go in from the start (albums.py); a
        failure only skips it (the music page still offers them)."""
        from .episode import Episode
        from .music import EpisodeMusic
        try:
            ep = Episode(self.ws, episode_id)
            try:
                m = EpisodeMusic(self.ws, ep)
                if m.series_suggestion():
                    m.apply_series()
            finally:
                ep.close()
        except Exception:      # noqa: BLE001 - the episode is usable without it
            traceback.print_exc()

    def _log_usage(self, episode_id: str, usage: dict) -> None:
        line = {"at": now(), "episode": episode_id, "kind": "first_cut", **usage}     # usage may set its own kind
        try:
            with self._usage_lock, open(self.ws.root / "ai_usage.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
        except OSError:
            pass
