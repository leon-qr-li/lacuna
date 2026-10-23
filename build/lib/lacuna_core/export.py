"""Export a timeline as a mastered WAV and/or MP3.

The master is always produced as a 24-bit WAV first (`master.py`); the MP3 is encoded from it
with ffmpeg/LAME and then decoded again to verify loudness and true peak after encoding, since
lossy coding can add a few tenths of a dB of inter-sample peak.
"""
from __future__ import annotations

import math
import os
import shutil
import subprocess
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np

from .edl import Timeline
from .master import LoudnessMeter, MasterReport, MasterSettings, Progress, master
from .media import SourcePool
from .render import RenderSettings, Renderer

FORMATS = ("wav", "mp3")


class ExportError(RuntimeError):
    pass


@dataclass
class ExportResult:
    files: dict[str, str] = field(default_factory=dict)       # format -> path
    report: MasterReport | None = None
    mp3: dict = field(default_factory=dict)                   # post-encode checks
    errors: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"files": dict(self.files), "report": self.report.to_dict() if self.report else None,
                "mp3": dict(self.mp3), "errors": dict(self.errors)}


def find_ffmpeg() -> str | None:
    return shutil.which("ffmpeg")


def timeline_source(pool: SourcePool, tl: Timeline, channels: int, base: RenderSettings = RenderSettings()):
    """Chunks of the raw mix with the renderer's peak soft-clip disabled (the master chain does
    peak control properly; float output may exceed 1.0 here)."""
    r = Renderer(pool, replace(base, channels=channels, ceiling_db=60.0, limit_db=60.1))
    return lambda: r.iter_chunks(tl)


def encode_mp3(wav: Path, mp3: Path, kbps: int = 128, tags: dict[str, str] | None = None,
               ffmpeg: str | None = None) -> None:
    ffmpeg = ffmpeg or find_ffmpeg()
    if not ffmpeg:
        raise ExportError("未找到 ffmpeg，无法导出 MP3")
    tmp = mp3.with_name(mp3.name + ".part")
    cmd = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav),
           "-codec:a", "libmp3lame", "-b:a", f"{int(kbps)}k", "-id3v2_version", "3"]
    for k, v in (tags or {}).items():
        if v:
            cmd += ["-metadata", f"{k}={v}"]
    cmd += ["-f", "mp3", str(tmp)]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise ExportError(f"MP3 编码失败：{p.stderr.strip()[-400:]}")
    os.replace(tmp, mp3)


def measure_file(path: Path, sr: int, channels: int, dual_mono: bool = True,
                 ffmpeg: str | None = None) -> tuple[float, float]:
    """Decode any file with ffmpeg (streamed, float32) and return (LUFS, dBTP)."""
    ffmpeg = ffmpeg or find_ffmpeg()
    if not ffmpeg:
        raise ExportError("未找到 ffmpeg")
    cmd = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-i", str(path),
           "-f", "f32le", "-ac", str(channels), "-ar", str(sr), "-"]
    m = LoudnessMeter(sr, channels, dual_mono)
    frame = 4 * channels
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as p:
        rest = b""
        while chunk := p.stdout.read(1 << 20):
            chunk = rest + chunk
            n = len(chunk) // frame * frame
            rest = chunk[n:]
            if n:
                m.add(np.frombuffer(chunk[:n], "<f4").reshape(-1, channels))
    if p.returncode != 0:
        raise ExportError(f"无法解码 {path.name}")
    return m.integrated(), m.true_peak_db()


def export(source, sr: int, channels: int, out_dir: str | Path, basename: str,
           formats: tuple[str, ...] = FORMATS, settings: MasterSettings = MasterSettings(),
           total: int = 0, mp3_kbps: int = 128, tags: dict[str, str] | None = None,
           progress: Progress | None = None) -> ExportResult:
    """Master `source` and write `<out_dir>/<basename>.wav|.mp3`.

    A failure of the MP3 step (e.g. no ffmpeg) keeps the WAV and is reported in `errors`."""
    formats = tuple(f for f in FORMATS if f in formats)
    if not formats:
        raise ExportError("没有选择导出格式")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    res = ExportResult()
    wav = out_dir / f"{basename}.wav"
    keep_wav = "wav" in formats
    if not keep_wav:
        wav = out_dir / f".{basename}.master.wav"
    share = 0.85 if "mp3" in formats else 1.0
    sub = (lambda f, msg: progress(f * share, msg)) if progress else None
    try:
        res.report = master(source, sr, channels, wav, settings, total, sub)
        if keep_wav:
            res.files["wav"] = str(wav)
        if "mp3" in formats:
            mp3 = out_dir / f"{basename}.mp3"
            try:
                if progress:
                    progress(0.86, "编码 MP3")
                encode_mp3(wav, mp3, mp3_kbps, tags)
                res.files["mp3"] = str(mp3)
                if progress:
                    progress(0.95, "检查 MP3")
                lufs, tp = measure_file(mp3, sr, channels, settings.dual_mono)
                res.mp3 = {"kbps": mp3_kbps,
                           "lufs": round(lufs, 2) if math.isfinite(lufs) else None,
                           "true_peak_db": round(tp, 2) if math.isfinite(tp) else None}
            except ExportError as e:
                res.errors["mp3"] = str(e)
    finally:
        if not keep_wav:
            wav.unlink(missing_ok=True)
    if progress:
        progress(1.0, "完成")
    return res
