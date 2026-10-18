"""New-episode import: two raw host tracks -> ASR -> features -> AI first cut -> reviewable episode.

One job at a time (CPU bound). Every finished step is written to ``<workspace>/imports/<id>/``
(ASR per track, tokens/features/editor document, each AI window), so a failed or interrupted
import resumes where it stopped instead of starting over. The raw tracks are only read; the new
episode references them by absolute path like every other episode (D29, read-only originals).

Steps and their share of the progress bar: models 4 % (first import only), ASR Leon 34 %,
ASR Pei 34 %, features 4 %, AI first cut 20 %, building the episode 4 %.
"""
from __future__ import annotations

import json
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import soundfile as sf

from lacuna_core.media import MediaRef, conform

from . import asr as asr_mod
from . import learning
from .ai_cut import TrackTokens, build_episode, report_dict
from .episode import create_episode
from .store import PathError, Workspace, atomic_write_json, check_id, inside, read_json
from .i18n import N_, tr

AUDIO_EXT = {".wav", ".flac", ".aif", ".aiff", ".mp3", ".m4a", ".ogg", ".opus", ".aac"}
HOSTS = (("L", "Leon"), ("P", "Pei"))
JOB_FILE = "job.json"
STEPS = (("models", 0.04), ("asr_L", 0.34), ("asr_P", 0.34), ("features", 0.04), ("first_cut", 0.20),
         ("episode", 0.04))
STEP_LABELS = {"models": N_("准备识别模型"), "asr_L": N_("识别 Leon 的分轨"), "asr_P": N_("识别 Pei 的分轨"),
               "features": N_("分析停顿、语速和重叠"), "first_cut": N_("AI 第一刀"), "episode": N_("生成审阅")}


class ImportBusy(RuntimeError):
    pass


class Cancelled(Exception):
    pass


class ImportError_(RuntimeError):
    """A problem the user can act on (message is Chinese)."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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
                 asr_backend: Any = None, models_dir: Path | None = None):
        from .first_cut import make_first_cut
        self.ws = ws
        self.root = ws.root / "imports"
        self.models_dir = Path(models_dir) if models_dir else ws.root / "models"
        self.first_cut_factory = first_cut_factory or (lambda: make_first_cut("auto"))
        self.asr_backend = asr_backend          # None = real sherpa-onnx ASR (tests inject a fake)
        self._lock = threading.Lock()
        self._usage_lock = threading.Lock()
        self._running: str | None = None
        self._cancel: set[str] = set()
        self.jobs: dict[str, dict] = {}
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
                job.update(state="interrupted", error=tr("App 在导入途中关闭了，点「继续」从断点接着做。"))
            self.jobs[job["id"]] = job

    def _save(self, job: dict) -> None:
        d = self.dir_for(job["id"])
        d.mkdir(parents=True, exist_ok=True)
        atomic_write_json(d / JOB_FILE, job)

    def status(self, episode_id: str | None = None):
        with self._lock:
            if episode_id is not None:
                j = self.jobs.get(episode_id)
                return dict(j) if j else None
            return sorted((dict(j) for j in self.jobs.values()), key=lambda j: j.get("created", ""), reverse=True)

    # ------------------------------------------------------------------ control
    def start(self, episode_id: str, title: str, leon: str, pei: str, wait: bool = False) -> dict:
        try:
            check_id(episode_id)
        except PathError:
            raise ImportError_(tr("剧集编号不能含 \\ / : * ? \" < > | 等字符"))
        if episode_id in self.ws.episode_ids():
            raise ImportError_(tr("已经有一集叫 {episode_id}，换个编号", episode_id=episode_id))
        tracks = {"L": check_track(leon), "P": check_track(pei)}
        if tracks["L"]["path"] == tracks["P"]["path"]:
            raise ImportError_(tr("Leon 和 Pei 选了同一个文件"))
        with self._lock:
            old = self.jobs.get(episode_id)
            if old and old["state"] in ("queued", "running"):
                raise ImportBusy(tr("这一集已经在导入"))
        job = {"id": episode_id, "title": title.strip() or episode_id, "tracks": tracks,
               "state": "queued", "progress": 0.0, "step": None, "stage": tr("排队"), "steps": {},
               "created": now(), "started": None, "finished": None, "error": None, "result": None}
        return self._launch(job, wait)

    def resume(self, episode_id: str, wait: bool = False) -> dict:
        with self._lock:
            job = self.jobs.get(episode_id)
        if job is None:
            raise KeyError(episode_id)
        if job["state"] not in ("error", "interrupted", "cancelled"):
            raise ImportBusy(tr("这一集不需要继续"))
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

    def _launch(self, job: dict, wait: bool) -> dict:
        with self._lock:
            if self._running:
                raise ImportBusy(tr("{_running} 正在导入，等它做完再导入下一集", _running=self._running))
            self._running = job["id"]
            self._cancel.discard(job["id"])
            self.jobs[job["id"]] = job
        self._save(job)
        if wait:
            self._run(job)
        else:
            threading.Thread(target=self._run, args=(job,), name=f"import-{job['id']}", daemon=True).start()
        return dict(job)

    # ------------------------------------------------------------------ the job
    def _progress(self, job: dict, step: str, frac: float, stage: str) -> None:
        if job["id"] in self._cancel:
            raise Cancelled()
        before = sum(w for s, w in STEPS[:[s for s, _ in STEPS].index(step)])
        weight = dict(STEPS)[step]
        with self._lock:
            job["step"] = step
            job["stage"] = stage
            job["progress"] = round(min(before + weight * min(max(frac, 0.0), 1.0), 0.999), 4)

    def _done_step(self, job: dict, step: str, info: dict | None = None) -> None:
        with self._lock:
            job["steps"][step] = {"done": now(), **(info or {})}
        self._save(job)

    def _run(self, job: dict) -> None:
        d = self.dir_for(job["id"])
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
                job.update(state="error", error=tr("{p0}出错：{p1}", p0=tr(STEP_LABELS.get(job.get('step'), N_('导入'))), p1=e or type(e).__name__),
                           finished=now())
        finally:
            with self._lock:
                job["elapsed_s"] = round(job.get("elapsed_s", 0) + time.monotonic() - t0, 1)
                self._running = None
                self._cancel.discard(job["id"])
            self._save(job)

    def _steps(self, job: dict, d: Path) -> None:
        backend = self.asr_backend
        # 1. models (real ASR only)
        if backend is None:
            if not asr_mod.sherpa_installed():
                raise ImportError_(tr("没装语音识别组件 sherpa-onnx（pip install -e \".[asr]\"）"))
            if not asr_mod.models_present(self.models_dir):
                asr_mod.ensure_models(self.models_dir, lambda f, s: self._progress(job, "models", f, s))
        self._done_step(job, "models")

        # 2. ASR per track (cached)
        rec = None
        audio16: dict[str, Any] = {}
        asr: dict[str, dict] = {}
        for tag, name in HOSTS:
            step = f"asr_{tag}"
            out = d / f"asr_{tag}.json"
            if out.is_file():
                asr[tag] = read_json(out)
                continue
            self._progress(job, step, 0.0, tr("解码 {name} 的分轨", name=name))
            t = time.monotonic()
            x = asr_mod.decode_16k(job["tracks"][tag]["path"])
            audio16[tag] = x
            if backend is None:
                if rec is None:
                    self._progress(job, step, 0.01, tr("加载识别模型"))
                    rec = asr_mod.load_recognizers(self.models_dir)
                res = asr_mod.transcribe(x, rec, lambda f, s, step=step, name=name:
                                         self._progress(job, step, f, f"{name}：{s}"))
            else:
                res = backend(tag, x, lambda f, s, step=step, name=name: self._progress(job, step, f, f"{name}：{s}"))
            atomic_write_json(out, res)
            asr[tag] = res
            self._done_step(job, step, {"seconds": round(time.monotonic() - t, 1),
                                        "segments": len(res["segments"]), "audio_s": res["audio_s"]})
        rec = None

        # 3. features + editor document (cached)
        from . import features
        tok_p, feat_p, doc_p = d / "tokens.json", d / "features.json", d / "editor_input.md"
        if not (tok_p.is_file() and feat_p.is_file() and doc_p.is_file()):
            self._progress(job, "features", 0.0, tr("分析停顿、语速和重叠"))
            for tag, _ in HOSTS:
                if tag not in audio16:
                    audio16[tag] = asr_mod.decode_16k(job["tracks"][tag]["path"])
            tokens_doc, feats, doc = features.build(asr, audio16, job["id"], log=lambda *_: None)
            atomic_write_json(feat_p, feats)
            atomic_write_json(tok_p, tokens_doc)
            doc_p.write_text(doc, encoding="utf-8")
            self._done_step(job, "features", {"tokens": {t: len(v) for t, v in tokens_doc["tracks"].items()}})
        audio16.clear()
        tokens_doc = read_json(tok_p)
        tokens = {tag: TrackTokens(t) for tag, t in tokens_doc["tracks"].items()}
        doc = doc_p.read_text(encoding="utf-8")

        # 4. AI first cut (each window cached)
        ops_p = d / "ops.json"
        if ops_p.is_file():
            ops_doc = read_json(ops_p)
        else:
            fc = self.first_cut_factory()
            if hasattr(fc, "on_usage"):
                fc.on_usage = lambda u: self._log_usage(job["id"], u)     # logged per call, failures included
            duration = max(a["audio_s"] for a in asr.values())
            extra = learning.prompt_rules(self.ws)      # rules Leon approved on 「学到的规则」 ("" if none)
            self._progress(job, "first_cut", 0.0, tr("AI 第一刀") if fc.name == "claude" else tr("规则第一刀（没有 Claude）"))
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
                    raise ImportError_(tr("AI 第一刀没做完：{e}。已剪好的段落都存着，点「继续」接着剪。", e=e))
                raise
            ops_doc = res.ops_doc
            atomic_write_json(ops_p, ops_doc)
            self._done_step(job, "first_cut", {"engine": fc.name, "ops": len(ops_doc["ops"]), "usage": res.usage})

        # 5. episode
        self._progress(job, "episode", 0.0, tr("生成审阅（核对音频）"))
        media = self._media(job, d)
        self._progress(job, "episode", 0.5, tr("生成审阅（精修剪辑点）"))
        project, edits, transcript, report = build_episode(media, ops_doc, tokens,
                                                           policy=learning.review_policy(self.ws))
        engine = job["steps"].get("first_cut", {}).get("engine", "claude")
        meta = {"title": job["title"], "demo": False, "raw_offset_s": 0.0, "source": "import",
                "ai_model": ops_doc.get("model", ""), "ai_notes": ops_doc.get("notes", ""),
                "ai_report": report_dict(report), "first_cut_engine": engine,
                "imported_at": now(), "raw_tracks": {name: job["tracks"][tag]["path"] for tag, name in HOSTS}}
        create_episode(self.ws, job["id"], meta, project, edits, transcript)
        self._level(job["id"])          # not cancellable: the episode exists now
        cons = sum(e.consequential for e in edits)
        dur = project.base.length / project.base.sample_rate
        with self._lock:
            job["result"] = {"episode": job["id"], "edits": len(edits), "to_review": cons,
                             "raw_duration": round(dur, 1),
                             "skipped": sum(report.skipped.values()), "engine": engine}
        self._done_step(job, "episode")

    def _media(self, job: dict, d: Path) -> dict[str, MediaRef]:
        """Raw tracks as MediaRefs (read in place); conformed to WAV only if they can't be."""
        refs: dict[str, MediaRef] = {}
        for tag, name in HOSTS:
            try:
                refs[name] = MediaRef.probe(job["tracks"][tag]["path"])
            except Exception:       # noqa: BLE001 - format libsndfile can't read
                refs[name] = None    # type: ignore[assignment]
        rates = {r.sample_rate for r in refs.values() if r is not None}
        if None in refs.values() or len(rates) > 1:
            sr = max(rates) if rates else 48000
            for tag, name in HOSTS:
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

    def _log_usage(self, episode_id: str, usage: dict) -> None:
        line = {"at": now(), "episode": episode_id, "kind": "first_cut", **usage}
        try:
            with self._usage_lock, open(self.ws.root / "ai_usage.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
        except OSError:
            pass


# ---------------------------------------------------------------------- file browser

def list_dir(path: str | None, default: Path) -> dict:
    """Folders and audio files in `path` (local machine; the app only ever binds to 127.0.0.1)."""
    import os
    import sys
    p = Path(path).expanduser() if path else default
    try:
        p = p.resolve()
        entries = list(os.scandir(p))
    except (OSError, RuntimeError):
        raise ImportError_(tr("打不开文件夹：{p}", p=p))
    dirs, files = [], []
    for e in entries:
        if e.name.startswith((".", "$")):
            continue
        try:
            if e.is_dir():
                dirs.append({"name": e.name, "path": str(p / e.name)})
            elif Path(e.name).suffix.lower() in AUDIO_EXT:
                f = {"name": e.name, "path": str(p / e.name), "size": e.stat().st_size, "duration": None}
                try:
                    i = sf.info(e.path)
                    f["duration"] = round(i.frames / i.samplerate, 1)
                except Exception:   # noqa: BLE001
                    pass
                files.append(f)
        except OSError:
            continue
    roots = [str(default)]
    if sys.platform == "win32":
        roots += [f"{c}:\\" for c in "CDEFGH" if Path(f"{c}:\\").exists()]
    else:
        roots += [str(Path.home()), "/"]
    parent = str(p.parent) if p.parent != p else None
    return {"path": str(p), "parent": parent, "dirs": sorted(dirs, key=lambda d: d["name"].lower()),
            "files": sorted(files, key=lambda f: f["name"].lower()), "roots": list(dict.fromkeys(roots))}
