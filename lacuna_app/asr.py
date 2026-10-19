"""Local verbatim ASR for a new episode: Silero VAD + a main recogniser (+ SenseVoice cross-check).

Same engines and settings as spike S2 / S5 (D30): sherpa-onnx int8 models on the CPU, one VAD
pass per track, and both recognisers decode the *same* VAD segments so their readings can be
compared token by token (``features.build_tokens`` flags disagreements). Audio never leaves the
machine; the models are downloaded once into ``<workspace>/models``.

The episode's language picks the engines (``ENGINES``):
* ``zh``: Paraformer-large zh + SenseVoice locked to zh (unchanged since S2);
* ``en``: Parakeet-TDT 0.6B v2 (cased, punctuated, keeps some um/uh) + SenseVoice locked to en.
  Both give sentencepiece pieces; they are merged into whole words here (``words_from_pieces``),
  so an English token is one word. Measured on a CC-BY English podcast (docs: 英文剪辑实测):
  Paraformer-zh 111 % WER, Parakeet 15 %.

Output per track (JSON, raw seconds of that track)::

    {"audio_s": 4411.9, "segments": [{"start", "end",
        "par": {"text", "tokens": [{"t", "start", "end"}]},
        "sv":  {"text", "event", "emotion", "tokens": [...]}}]}
"""
from __future__ import annotations

import os
import subprocess
import tarfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from lacuna_core.media import resample_filter
from .i18n import tr

SR = 16000
RELEASES = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
PARAFORMER = "sherpa-onnx-paraformer-zh-2023-09-14"
PARAKEET = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
SENSEVOICE = "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17"
VAD = "silero_vad.onnx"
LANGUAGES = ("zh", "en")
# (file that proves the model is there, download name, approx. download bytes for progress)
_PARAFORMER = (f"{PARAFORMER}/model.int8.onnx", f"{PARAFORMER}.tar.bz2", 234_051_698)
_PARAKEET = (f"{PARAKEET}/encoder.int8.onnx", f"{PARAKEET}.tar.bz2", 482_468_385)
_SENSEVOICE = (f"{SENSEVOICE}/model.int8.onnx", f"{SENSEVOICE}.tar.bz2", 163_002_883)
_VAD = (VAD, VAD, 643_854)
ENGINES = {"zh": (_PARAFORMER, _SENSEVOICE, _VAD), "en": (_PARAKEET, _SENSEVOICE, _VAD)}
MODELS = ENGINES["zh"]


def language(code: str | None) -> str:
    """A supported episode language (anything else: zh, what every episode was before)."""
    return code if code in LANGUAGES else "zh"

Progress = Callable[[float, str], None]       # (fraction 0..1, Chinese stage text)


def sherpa_installed() -> bool:
    try:
        import sherpa_onnx  # noqa: F401
    except ImportError:
        return False
    return True


def models_present(models_dir: Path, lang: str = "zh") -> bool:
    return all((Path(models_dir) / probe).is_file() for probe, _, _ in ENGINES[language(lang)])


def ensure_models(models_dir: Path, progress: Progress = lambda f, s: None,
                  base_url: str = RELEASES, lang: str = "zh") -> None:
    """Download and unpack any missing model of `lang` (zh ~400 MB, en ~650 MB, once). Partial
    downloads never count."""
    models_dir = Path(models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)
    missing = [m for m in ENGINES[language(lang)] if not (models_dir / m[0]).is_file()]
    total = sum(m[2] for m in missing) or 1
    done = 0
    for probe, name, size in missing:
        part = models_dir / (name + ".part")
        with urllib.request.urlopen(base_url + name, timeout=60) as r, open(part, "wb") as f:
            got = 0
            while chunk := r.read(1 << 20):
                f.write(chunk)
                got += len(chunk)
                progress(min((done + got) / total, 1.0), tr("下载识别模型（一次性，约 {p1} MB）{p0} MB", p0=f"{(done + got) / 1e6:.0f}",
                                          p1=f"{total / 1e6:.0f}"))
        if name.endswith(".tar.bz2"):
            with tarfile.open(part, "r:bz2") as t:
                t.extractall(models_dir, filter="data")
            part.unlink()
        else:
            part.replace(models_dir / name)
        if not (models_dir / probe).is_file():
            raise RuntimeError(tr("模型文件不完整：{probe}", probe=probe))
        done += size


def decode_16k(src: str | Path) -> np.ndarray:
    """Mono 16 kHz float32 of any file ffmpeg can read (the source file is only read)."""
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-i", str(src),
           "-ac", "1", "-af", resample_filter(SR), "-f", "f32le", "-"]
    out = subprocess.run(cmd, check=True, capture_output=True).stdout
    return np.frombuffer(out, dtype="<f4").copy()


def vad_segments(audio: np.ndarray, vad_model: str, threshold: float = 0.5, min_silence: float = 0.3,
                 min_speech: float = 0.2, max_speech: float = 20.0, pad: float = 0.2,
                 progress: Callable[[float], None] = lambda f: None) -> list[tuple[float, float]]:
    """Speech segments via sherpa-onnx Silero VAD, padded and merged (spike S2 settings)."""
    import sherpa_onnx as so

    cfg = so.VadModelConfig()
    cfg.silero_vad.model = vad_model
    cfg.silero_vad.threshold = threshold
    cfg.silero_vad.min_silence_duration = min_silence
    cfg.silero_vad.min_speech_duration = min_speech
    cfg.silero_vad.max_speech_duration = max_speech
    cfg.sample_rate = SR
    win = cfg.silero_vad.window_size
    vad = so.VoiceActivityDetector(cfg, buffer_size_in_seconds=600)
    segs: list[tuple[float, float]] = []

    def drain():
        while not vad.empty():
            s = vad.front
            segs.append((s.start / SR, (s.start + len(s.samples)) / SR))
            vad.pop()

    step = win * 2000
    for i in range(0, len(audio), win):
        vad.accept_waveform(audio[i:i + win])
        drain()
        if i % step == 0:
            progress(i / max(len(audio), 1))
    vad.flush()
    drain()
    dur = len(audio) / SR
    padded: list[tuple[float, float]] = []
    for a, b in segs:
        a, b = max(0.0, a - pad), min(dur, b + pad)
        if padded and a <= padded[-1][1]:
            padded[-1] = (padded[-1][0], b)
        else:
            padded.append((a, b))
    return padded


def tokens_from_starts(toks, starts, seg_start: float, seg_end: float, durations=None) -> list[dict]:
    """Token dicts in raw seconds; without durations, end = next start (capped at +0.6 s)."""
    out = []
    for i, (t, st) in enumerate(zip(toks, starts)):
        a = seg_start + float(st)
        if durations:
            b = a + float(durations[i])
        elif i + 1 < len(starts):
            b = min(seg_start + float(starts[i + 1]), a + 0.6)
        else:
            b = min(seg_end, a + 0.6)
        out.append({"t": t, "start": round(a, 3), "end": round(b, 3)})
    return out


def words_from_pieces(pieces: list[dict]) -> list[dict]:
    """Sentencepiece pieces (a new word starts with "▁" or a space) -> one token per word, from the
    first piece's start to the last piece's end. Pieces without a word-start mark join the word
    before them ("▁exper" "ience," -> "experience,")."""
    out: list[dict] = []
    for p in pieces:
        raw = p["t"]
        piece = raw.replace("▁", " ").strip()
        if not piece:
            continue
        if raw[:1] in (" ", "▁") or not out:
            out.append(dict(p, t=piece))
        else:
            out[-1]["t"] += piece
            out[-1]["end"] = p["end"]
    return out


@dataclass
class Recognizers:
    paraformer: object          # the main recogniser: Paraformer (zh) or Parakeet (en)
    sensevoice: object
    vad_model: str
    lang: str = "zh"


def load_recognizers(models_dir: Path, threads: int | None = None, lang: str = "zh") -> Recognizers:
    import sherpa_onnx as so

    m = Path(models_dir)
    lang = language(lang)
    threads = threads or max(1, min(8, (os.cpu_count() or 4) // 2))
    if lang == "en":
        main = so.OfflineRecognizer.from_transducer(
            encoder=str(m / PARAKEET / "encoder.int8.onnx"), decoder=str(m / PARAKEET / "decoder.int8.onnx"),
            joiner=str(m / PARAKEET / "joiner.int8.onnx"), tokens=str(m / PARAKEET / "tokens.txt"),
            model_type="nemo_transducer", num_threads=threads)
    else:
        main = so.OfflineRecognizer.from_paraformer(paraformer=str(m / PARAFORMER / "model.int8.onnx"),
                                                    tokens=str(m / PARAFORMER / "tokens.txt"), num_threads=threads)
    sv = so.OfflineRecognizer.from_sense_voice(model=str(m / SENSEVOICE / "model.int8.onnx"),
                                               tokens=str(m / SENSEVOICE / "tokens.txt"),
                                               num_threads=threads, language=lang, use_itn=False)
    return Recognizers(main, sv, str(m / VAD), lang)


def _decode(recognizer, chunk: np.ndarray):
    st = recognizer.create_stream()
    st.accept_waveform(SR, chunk)
    recognizer.decode_stream(st)
    return st.result


def transcribe(audio: np.ndarray, rec: Recognizers, progress: Progress = lambda f, s: None) -> dict:
    """VAD once, then the main recogniser and SenseVoice on every segment (English: pieces merged
    into words).

    The two recognisers decode each segment at the same time (SenseVoice on a worker thread;
    sherpa-onnx releases the GIL), each with the thread count `load_recognizers` gave it, so the
    CPU is used fully and every result is identical to decoding one after the other."""
    dur = len(audio) / SR
    words = getattr(rec, "lang", "zh") == "en"
    segs = vad_segments(audio, rec.vad_model, progress=lambda f: progress(0.05 * f, tr("找说话段落")))
    out = []
    with ThreadPoolExecutor(1, thread_name_prefix="sensevoice") as pool:
        for k, (s0, s1) in enumerate(segs):
            chunk = audio[int(s0 * SR):int(s1 * SR)]
            sv_job = pool.submit(_decode, rec.sensevoice, chunk)
            r = _decode(rec.paraformer, chunk)
            par_toks = tokens_from_starts(list(r.tokens), list(r.timestamps), s0, s1,
                                          list(getattr(r, "durations", []) or []))
            par = {"text": r.text.strip(), "tokens": words_from_pieces(par_toks) if words else par_toks}
            r = sv_job.result()
            sv_toks = tokens_from_starts(list(r.tokens), list(r.timestamps), s0, s1)
            sv = {"text": r.text, "event": (getattr(r, "event", "") or "").strip("<|>") or None,
                  "emotion": (getattr(r, "emotion", "") or "").strip("<|>") or None,
                  "tokens": words_from_pieces(sv_toks) if words else sv_toks}
            out.append({"start": round(s0, 3), "end": round(s1, 3), "par": par, "sv": sv})
            if k % 10 == 0:
                progress(0.05 + 0.95 * s1 / max(dur, 1e-9), tr("逐字识别 {p0}/{p1} 分钟", p0=int(s1 // 60), p1=int(dur // 60)))
    return {"audio_s": round(dur, 3), "segments": out}
