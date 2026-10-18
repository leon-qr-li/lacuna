"""Media library: Leon's music, series jingles and film clips, with credits (D45).

Layout (all under ``<workspace>/library/``)::

    library.json                 index (schema 1): assets + series rules
    music/ jingles/ clips/ other/   the files themselves (uploaded from the browser, or dropped there by Leon)
    _removed/                    files taken out of the library (never deleted)
    .cache/                      decoded copies at a project sample rate (disposable)

Source files are never modified. An asset's id is derived from its content hash, so the same
file added twice is one asset and renaming the file does not change it.

Credits: Leon may only say "这是《奥德赛》的主题曲". `lookup_credit` asks Claude (with web search)
for the official title / composer / album; the answer is stored as *suggested* until Leon confirms
it. Only text (file name, embedded tags, Leon's note, duration) is sent, never audio.

Other modules read the library only through this module (D42).
"""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from lacuna_core import MediaRef, content_hash
from lacuna_core.master import LoudnessMeter
from lacuna_core.media import resample_filter

from .store import PathError, Workspace, atomic_write_json, inside, read_json, now_iso as _now
from .i18n import AI_NAME_RULE, N_, lang, tr

SCHEMA = 1
INDEX = "library.json"
# What Leon uses an asset for (his fixed list, 2026-10-17). The music page takes the placement
# role from it, so an intro goes to the start and a trailer is inserted like a clip.
KINDS = {
    "intro": N_("片头（播客开始）"), "outro": N_("片尾（播客结尾）"), "interlude": N_("休息间隙"),
    "bed": N_("聊天背景音"), "dialogue": N_("电影对白 / sample"), "trailer": N_("预告片 trailer"), "other": N_("其他素材"),
}
ROLE_FOR_KIND = {"intro": "intro", "outro": "outro", "interlude": "interlude", "bed": "bed",
                 "dialogue": "clip", "trailer": "clip", "other": "interlude"}
FOLDERS = {"intro": "jingles", "outro": "jingles", "interlude": "music", "bed": "music",
           "dialogue": "clips", "trailer": "clips", "other": "other"}
SCAN_KIND = {"jingles": "intro", "music": "interlude", "clips": "dialogue", "other": "other"}
LEGACY_KIND = {"jingle": "intro", "music": "interlude", "clip": "dialogue"}   # the first three kinds (#23)
AUDIO_EXT = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".aif", ".aiff", ".wma"}
CREDIT_FIELDS = ("title", "artist", "composer", "album", "film", "year")
CONFIRMED, SUGGESTED, UNKNOWN = "confirmed", "suggested", "unknown"
ANALYSIS_SR = 48000


class LibraryError(ValueError):
    """Bad request against the library (unknown kind, not an audio file ...)."""


def _ffprobe(path: Path) -> dict:
    """Format/stream info and embedded tags; {} when ffprobe is missing or fails."""
    exe = shutil.which("ffprobe")
    if not exe:
        return {}
    try:
        out = subprocess.run([exe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams",
                              "-select_streams", "a:0", str(path)], capture_output=True, timeout=60)
        return json.loads(out.stdout.decode("utf-8", "replace") or "{}")
    except (OSError, ValueError, subprocess.SubprocessError):
        return {}


def _tags(probe: dict) -> dict:
    raw = {**(probe.get("streams") or [{}])[0].get("tags", {}), **probe.get("format", {}).get("tags", {})}
    low = {k.lower(): str(v).strip() for k, v in raw.items() if str(v).strip()}
    out = {k: low[k] for k in ("title", "artist", "album", "album_artist", "composer", "date", "genre") if k in low}
    return out


def decode(src: Path, dst: Path, sample_rate: int, layout: str) -> MediaRef:
    """Decode `src` once to a float WAV at `sample_rate`: layout "m" = mono downmix, "L"/"R" = one
    channel of a stereo file (a mono file gives the same signal for both)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.stem + ".part.wav")
    pan = {"m": None, "L": "pan=mono|c0=c0", "R": "pan=mono|c0=c1"}[layout]
    probe_ch = 1
    if pan:
        probe = _ffprobe(src)
        probe_ch = int((probe.get("streams") or [{}])[0].get("channels") or 2)
        if probe_ch < 2:
            pan = None
    af = ",".join(x for x in (pan, resample_filter(sample_rate)) if x)
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-vn"]
    if not pan:
        cmd += ["-ac", "1"]
    cmd += ["-af", af, "-c:a", "pcm_f32le", str(tmp)]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except FileNotFoundError as e:
        raise LibraryError(tr("没有找到 ffmpeg，无法读取这个音频文件")) from e
    except subprocess.CalledProcessError as e:
        tmp.unlink(missing_ok=True)    # ffmpeg may leave half a file behind
        raise LibraryError(tr("读不了这个音频文件：{p0}", p0=e.stderr.decode('utf-8', 'replace')[-200:].strip())) from e
    os.replace(tmp, dst)
    return MediaRef.probe(dst, media_id=f"lib:{dst.stem}")


def loudness(path: Path) -> tuple[float, float]:
    """(integrated LUFS, sample peak dBFS) of a mono float WAV, read in chunks."""
    import soundfile as sf
    import numpy as np
    meter = LoudnessMeter(ANALYSIS_SR, 1, dual_mono=True, true_peak=False)
    peak = 0.0
    with sf.SoundFile(str(path)) as f:
        for block in f.blocks(blocksize=ANALYSIS_SR * 10, dtype="float32"):
            meter.add(block)
            peak = max(peak, float(np.abs(block).max(initial=0.0)))
    lufs = meter.integrated()
    return (round(lufs, 2) if math.isfinite(lufs) else None), (round(20 * math.log10(peak), 2) if peak > 0 else None)


def credit_line(asset: dict) -> str:
    """Printable credit, e.g. 《奥德赛》原声 · Ludwig Göransson — “Theme”. Falls back to the file name."""
    c = asset.get("credit") or {}
    title, film = c.get("title"), c.get("film")
    who = c.get("composer") or c.get("artist")
    if not title and not film:
        return Path(asset.get("name") or asset.get("file") or "未知曲目").stem  # i18n-ignore
    parts = []
    if film:
        parts.append(f"《{film}》原声")  # i18n-ignore
    elif c.get("album"):
        parts.append(f"《{c['album']}》")
    if who:
        parts.append(who)
    head = " · ".join(parts)
    if title:
        return f"{head} — “{title}”" if head else f"“{title}”"
    return head


class Library:
    def __init__(self, ws: Workspace):
        self.ws = ws
        self.dir = ws.root / "library"
        self.index_path = self.dir / INDEX
        self.lock = threading.RLock()

    # ------------------------------------------------------------------ storage
    def load(self) -> dict:
        with self.lock:
            if not self.index_path.exists() and not self.index_path.with_name(INDEX + ".bak").exists():
                return {"schema": SCHEMA, "assets": [], "series": []}
            doc = read_json(self.index_path)
            if doc.get("schema") != SCHEMA:
                raise ValueError(f"unsupported library schema {doc.get('schema')}")
            doc.setdefault("series", [])
            for a in doc["assets"]:
                k = a.get("kind")
                a["kind"] = k if k in KINDS else LEGACY_KIND.get(k, "other")
            return doc

    def save(self, doc: dict) -> None:
        with self.lock:
            self.dir.mkdir(parents=True, exist_ok=True)
            atomic_write_json(self.index_path, doc)

    def assets(self) -> list[dict]:
        return self.load()["assets"]

    def asset(self, asset_id: str) -> dict:
        for a in self.assets():
            if a["id"] == asset_id:
                return a
        raise KeyError(asset_id)

    def path_of(self, asset: dict) -> Path:
        return inside(self.dir, *Path(asset["file"]).parts)

    # ------------------------------------------------------------------ adding
    def add_file(self, src: str | Path, kind: str = "other", note: str = "") -> dict:
        """Copy an audio file into the library (unless it already lives there) and analyse it.
        The same content added again returns the existing asset (note updated if given)."""
        if kind not in KINDS:
            raise LibraryError(f"unknown kind {kind!r}")
        src = Path(src).expanduser()
        if not src.is_file():
            raise LibraryError(tr("找不到文件：{src}", src=src))
        if src.suffix.lower() not in AUDIO_EXT:
            raise LibraryError(tr("不是支持的音频文件：{name}", name=src.name))
        sha = content_hash(src).split(":", 1)[1]
        aid = "a_" + sha[:12]
        with self.lock:
            doc = self.load()
            old = next((a for a in doc["assets"] if a["id"] == aid), None)
            if old:
                if note:
                    old["note"] = note
                    self.save(doc)
                return old
        dst_dir = self.dir / FOLDERS[kind]
        root = self.dir.resolve()
        if root in src.resolve().parents:
            dst = src.resolve()
        else:
            dst_dir.mkdir(parents=True, exist_ok=True)
            dst = dst_dir / src.name
            n = 1
            while dst.exists():
                dst = dst_dir / f"{src.stem} ({n}){src.suffix}"
                n += 1
            tmp = dst.with_name(dst.name + ".part")
            shutil.copyfile(src, tmp)
            os.replace(tmp, dst)
        asset = self._analyse(aid, sha, dst, kind, note)
        with self.lock:
            doc = self.load()
            if not any(a["id"] == aid for a in doc["assets"]):
                doc["assets"].append(asset)
                self.save(doc)
        return asset

    def _analyse(self, aid: str, sha: str, path: Path, kind: str, note: str) -> dict:
        probe = _ffprobe(path)
        tags = _tags(probe)
        stream = (probe.get("streams") or [{}])[0]
        ref = self.decoded_path(aid, ANALYSIS_SR, "m")
        m = decode(path, ref, ANALYSIS_SR, "m") if not ref.exists() else MediaRef.probe(ref, f"lib:{ref.stem}")
        lufs, peak = loudness(ref)
        credit: dict[str, Any] = {k: None for k in CREDIT_FIELDS} | {"status": UNKNOWN, "source": None, "sources": []}
        if tags.get("title"):
            credit.update(title=tags.get("title"), artist=tags.get("artist") or tags.get("album_artist"),
                          composer=tags.get("composer"), album=tags.get("album"), status=SUGGESTED, source="file_tags")
            year = (tags.get("date") or "")[:4]
            credit["year"] = int(year) if year.isdigit() else None
        return {
            "id": aid, "kind": kind, "file": path.relative_to(self.dir.resolve()).as_posix(), "name": path.name,
            "sha256": sha, "duration_s": round(m.frames / m.sample_rate, 3),
            "sample_rate": int(stream.get("sample_rate") or 0) or None, "channels": int(stream.get("channels") or 0) or None,
            "lufs": lufs, "peak_db": peak, "added_at": _now(), "note": note, "tags": tags, "credit": credit,
        }

    def scan(self) -> list[dict]:
        """Index audio files Leon dropped into the library folders by hand. Returns the new assets."""
        known = {a["file"] for a in self.assets()}
        new = []
        for folder, kind in SCAN_KIND.items():
            d = self.dir / folder
            if not d.is_dir():
                continue
            for p in sorted(d.rglob("*")):
                if p.is_file() and p.suffix.lower() in AUDIO_EXT and not p.name.endswith(".part"):
                    rel = p.resolve().relative_to(self.dir.resolve()).as_posix()
                    if rel not in known:
                        new.append(self.add_file(p, kind))
        return new

    def upload_target(self, name: str, kind: str) -> Path:
        """Reserve a fresh ``<folder>/<name>.part`` for a file uploaded from the browser (dragged
        in or picked). Only the base name is kept, so the upload can never land outside the folder."""
        if kind not in KINDS:
            raise LibraryError(f"unknown kind {kind!r}")
        base = name.replace("\\", "/").rsplit("/", 1)[-1]
        base = "".join(c for c in base if c not in '<>:"|?*' and ord(c) >= 32).strip(" .")
        stem, ext = os.path.splitext(base)
        if not stem or ext.lower() not in AUDIO_EXT:
            raise LibraryError(tr("不是支持的音频文件：{name}", name=name))
        d = self.dir / FOLDERS[kind]
        d.mkdir(parents=True, exist_ok=True)
        for n in range(1000):
            dst = d / (base if n == 0 else f"{stem} ({n}){ext}")
            part = dst.with_name(dst.name + ".part")
            if dst.exists():
                continue
            try:
                part.open("xb").close()
                return part
            except FileExistsError:
                continue
        raise LibraryError(tr("同名文件太多：{base}", base=base))

    def add_upload(self, part: Path, kind: str, note: str = "") -> tuple[dict, bool]:
        """Finish an upload written to `upload_target`'s path. Returns (asset, duplicate): music
        already in the library under another name is not kept twice."""
        dst = part.with_name(part.name[: -len(".part")])
        os.replace(part, dst)
        try:
            asset = self.add_file(dst, kind, note)
        except Exception:
            dst.unlink(missing_ok=True)
            raise
        duplicate = self.path_of(asset).resolve() != dst.resolve()
        if duplicate:
            dst.unlink(missing_ok=True)
        return asset, duplicate

    def ensure_dirs(self) -> None:
        for folder in SCAN_KIND:
            (self.dir / folder).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ editing
    def update(self, asset_id: str, *, note: str | None = None, kind: str | None = None,
               credit: dict | None = None, confirm: bool = False) -> dict:
        """Change Leon's note / kind; `credit` overwrites the given credit fields (Leon's own
        correction, so it counts as confirmed); `confirm` accepts the current credit as is."""
        with self.lock:
            doc = self.load()
            a = next((x for x in doc["assets"] if x["id"] == asset_id), None)
            if a is None:
                raise KeyError(asset_id)
            if note is not None:
                a["note"] = note.strip()
            if kind is not None:
                if kind not in KINDS:
                    raise LibraryError(f"unknown kind {kind!r}")
                a["kind"] = kind
            if credit:
                c = a["credit"]
                for k in CREDIT_FIELDS:
                    if k in credit:
                        v = credit[k]
                        if k == "year":
                            v = int(v) if str(v or "").strip().isdigit() else None
                        else:
                            v = (str(v).strip() or None) if v is not None else None
                        c[k] = v
                c.update(status=CONFIRMED, source="leon", checked_at=_now())
            if confirm:
                a["credit"].update(status=CONFIRMED, checked_at=_now())
            self.save(doc)
            return a

    def set_suggestion(self, asset_id: str, found: dict, sources: list[str]) -> dict:
        with self.lock:
            doc = self.load()
            a = next((x for x in doc["assets"] if x["id"] == asset_id), None)
            if a is None:
                raise KeyError(asset_id)
            c = {k: found.get(k) for k in CREDIT_FIELDS}
            c["year"] = int(c["year"]) if isinstance(c["year"], (int, float)) or str(c["year"] or "").isdigit() else None
            a["credit"] = c | {"status": SUGGESTED if (c["title"] or c["film"]) else UNKNOWN, "source": "claude",
                               "sources": sources[:5], "note": found.get("note") or "", "checked_at": _now()}
            self.save(doc)
            return a

    def remove(self, asset_id: str) -> None:
        """Take an asset out of the library: its file moves to _removed/ (nothing is deleted)."""
        with self.lock:
            doc = self.load()
            a = next((x for x in doc["assets"] if x["id"] == asset_id), None)
            if a is None:
                raise KeyError(asset_id)
            try:
                p = self.path_of(a)
                if p.is_file():
                    dst = self.dir / "_removed" / p.name
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    if dst.exists():
                        dst = dst.with_name(f"{p.stem}_{int(time.time())}{p.suffix}")
                    os.replace(p, dst)
            except (OSError, PathError):
                pass
            doc["assets"] = [x for x in doc["assets"] if x["id"] != asset_id]
            self.save(doc)

    # ------------------------------------------------------------------ decoded copies for rendering
    def decoded_path(self, asset_id: str, sample_rate: int, layout: str) -> Path:
        return self.dir / ".cache" / f"{asset_id}_{sample_rate}_{layout}.wav"

    def media(self, asset: dict, sample_rate: int, layout: str) -> MediaRef:
        """Decoded copy of an asset at `sample_rate` ("m" mono, "L"/"R" stereo halves); made once."""
        dst = self.decoded_path(asset["id"], sample_rate, layout)
        with self.lock:
            if dst.exists():
                return MediaRef.probe(dst, media_id=f"lib:{dst.stem}")
            return decode(self.path_of(asset), dst, sample_rate, layout)

    # ------------------------------------------------------------------ series rules
    def series(self) -> list[dict]:
        return self.load()["series"]

    def save_series(self, name: str, intro: dict | None, outro: dict | None, default: bool = True) -> dict:
        """Remember an intro/outro as a series rule ("这个片头是 90 年代系列的"); `intro`/`outro`
        are placement templates (asset_id and the placement's tuning, music.TUNING)."""
        name = name.strip()
        if not name:
            raise LibraryError(tr("系列名不能为空"))
        keep = ("asset_id", "src_in_s", "src_out_s", "gain_db", "solo_s", "ramp_s", "bg_db", "pre_s", "bye_s", "fade_out_s",
                "overlap_s")    # overlap_s: only in rules saved before the full-play rule
        rule = {"name": name, "intro": {k: intro.get(k) for k in keep} if intro else None,
                "outro": {k: outro.get(k) for k in keep} if outro else None, "default": default, "updated_at": _now()}
        with self.lock:
            doc = self.load()
            doc["series"] = [s for s in doc["series"] if s["name"] != name]
            if default:
                for s in doc["series"]:
                    s["default"] = False
            doc["series"].append(rule)
            self.save(doc)
        return rule

    def series_rule(self, name: str | None = None) -> dict | None:
        rules = self.series()
        if name:
            return next((s for s in rules if s["name"] == name), None)
        return next((s for s in rules if s.get("default")), None)

    @staticmethod
    def asset_view(a: dict) -> dict:
        return a | {"kind_label": tr(KINDS.get(a["kind"], a["kind"])), "credit_line": credit_line(a)}

    def view(self) -> dict:
        assets = [self.asset_view(a) for a in self.assets()]
        return {"assets": sorted(assets, key=lambda a: a["added_at"], reverse=True), "series": self.series(),
                "folder": str(self.dir), "kinds": {k: tr(v) for k, v in KINDS.items()}, "kind_roles": ROLE_FOR_KIND}


# ===================================================================== credit lookup (Claude + web search)

# Claude can't hear the audio; without Leon's note it only has the file name, so the lookup isn't worth a call
NEED_NOTE = N_("先在备注里写一句这是什么曲子（比如哪部电影的配乐），LACUNA 听不到音乐，只能按备注去查。")

LOOKUP_SYSTEM = """\
You identify the music Leon uses in 《洛城二三事》, a Chinese film podcast, so the show notes can \
credit it correctly. You get a file name, the tags embedded in the file (may be empty or wrong), \
its duration, and Leon's own casual note (for example "这是《奥德赛》的主题曲" = "this is the theme \
of The Odyssey"). Find the official track: the exact title as released on the official soundtrack \
album, the composer (or performing artist for a song), the album, the film or series it belongs to \
(use the title most commonly used in mainland China in Simplified Chinese, plus nothing else), and \
the release year. Use web search to confirm; prefer the official soundtrack listing, the label, \
Apple Music / Spotify, or Wikipedia over fan pages. If the duration does not match the track you \
found, mention it in note. Never invent a title: when you cannot identify the track with \
reasonable confidence, return null fields and say why in note. Then call submit_credit once.""" + AI_NAME_RULE  # i18n-ignore

NOTE_FOR_LEON = "one short sentence in Simplified Chinese for Leon"
CREDIT_TOOL = {
    "name": "submit_credit",
    "description": "Submit the identified track (null for anything not known).",
    "strict": True,
    "input_schema": {
        "type": "object", "additionalProperties": False,
        "required": ["title", "artist", "composer", "album", "film", "year", "confidence", "note"],
        "properties": {
            "title": {"type": ["string", "null"], "description": "official track title, original language"},
            "artist": {"type": ["string", "null"], "description": "performer, if a song"},
            "composer": {"type": ["string", "null"]},
            "album": {"type": ["string", "null"], "description": "soundtrack album title"},
            "film": {"type": ["string", "null"], "description": "film / series title in Simplified Chinese"},
            "year": {"type": ["integer", "null"]},
            "confidence": {"type": "number", "description": "0..1"},
            "note": {"type": "string", "description": NOTE_FOR_LEON},
        },
    },
}


def _credit_tool() -> dict:
    """The note is for Leon, in the interface language; the credit itself stays Chinese (show notes)."""
    if lang() != "en":
        return CREDIT_TOOL
    return json.loads(json.dumps(CREDIT_TOOL).replace(json.dumps(NOTE_FOR_LEON)[1:-1], "one short sentence for Leon, in English"))


def lookup_request(asset: dict) -> dict:
    info = {"file_name": asset.get("name"), "embedded_tags": asset.get("tags") or {},
            "duration_s": asset.get("duration_s"), "leons_note": asset.get("note") or "",
            "used_as": KINDS.get(asset.get("kind"), "")}
    return dict(model="claude-opus-5-5", max_tokens=16000, system=LOOKUP_SYSTEM,
                output_config={"effort": "medium"},
                tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 5}, _credit_tool()],
                tool_choice={"type": "auto"},
                messages=[{"role": "user", "content": json.dumps(info, ensure_ascii=False)}])


def lookup_credit(lib: Library, asset_id: str, client: Any = None) -> dict:
    """Ask Claude for the official credit of an asset; stores it as a suggestion.
    Returns {"asset", "message", "usage"}; failures come back as a message, nothing changes."""
    from .editor import ClaudeEditorAdapter, error_message, find_api_key, sdk_installed
    asset = lib.asset(asset_id)
    if not (asset.get("note") or "").strip():      # nothing to search for: don't spend a call
        return {"asset": asset, "message": tr(NEED_NOTE), "usage": None}
    if client is None:
        key, _ = find_api_key()
        if not key or not sdk_installed():
            return {"asset": asset, "message": tr("还没接上 AI（没有 AI 密钥），没法查曲名。"), "usage": None}
        import anthropic
        client = anthropic.Anthropic(api_key=key, timeout=180.0, max_retries=1)
    req = lookup_request(asset)
    t0 = time.monotonic()
    usage = None
    try:
        messages = list(req.pop("messages"))
        resp = None
        for _ in range(4):           # web search may pause a long turn; continue it
            resp = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default",
                                               messages=messages, **req)
            if resp.stop_reason != "pause_turn":
                break
            messages = messages + [{"role": "assistant", "content": resp.content}]
    except Exception as e:      # noqa: BLE001 - every failure becomes a message
        return {"asset": asset, "message": error_message(e, tail=tr("，曲名没有变。")), "usage": None}
    usage = ClaudeEditorAdapter._usage(resp, time.monotonic() - t0)
    sources = []
    found = None
    for block in resp.content:
        if block.type == "web_search_tool_result" and isinstance(getattr(block, "content", None), list):
            sources += [r.url for r in block.content if getattr(r, "url", None)]
        if block.type == "tool_use" and block.name == "submit_credit":
            found = dict(block.input)
    if resp.stop_reason == "refusal" or found is None:
        text = "".join(getattr(b, "text", "") for b in resp.content if b.type == "text").strip()
        return {"asset": asset, "message": text or tr("LACUNA 没有给出曲名。"), "usage": usage}
    asset = lib.set_suggestion(asset_id, found, list(dict.fromkeys(sources)))
    msg = found.get("note") or ""
    if not (found.get("title") or found.get("film")):
        msg = msg or tr("没查到可靠的曲名。")
    return {"asset": Library.asset_view(asset), "message": msg, "usage": usage}
