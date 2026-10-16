"""Whisper large-v3 / turbo via sherpa-onnx (int8 ONNX export of the OpenAI weights).

Used here because huggingface.co (faster-whisper CTranslate2 weights) is unreachable
from the spike container while GitHub release assets are. Greedy decoding, no prompt.

--chunking vad   : Silero VAD segments (production-like)
--chunking fixed : blind 30 s windows, no VAD (tests hallucination on silence / bleed)

Usage:
  python run_sherpa_whisper.py --audio X.wav --models MODELS_DIR --variant turbo --out out/x.json
"""
import argparse
import os
import time

import sherpa_onnx as so

from common import SR, Timer, fixed_chunks, load_wav, silero_segments, tokens_from_starts, write_result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True)
    ap.add_argument("--models", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--variant", default="turbo", choices=["turbo", "large-v3"])
    ap.add_argument("--chunking", default="vad", choices=["vad", "fixed"])
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--token-timestamps", action="store_true")
    a = ap.parse_args()

    md = os.path.join(a.models, f"sherpa-onnx-whisper-{a.variant}")
    v = a.variant
    t0 = time.perf_counter()
    rec = so.OfflineRecognizer.from_whisper(
        encoder=os.path.join(md, f"{v}-encoder.int8.onnx"), decoder=os.path.join(md, f"{v}-decoder.int8.onnx"),
        tokens=os.path.join(md, f"{v}-tokens.txt"), language="zh", task="transcribe",
        num_threads=a.threads, enable_token_timestamps=a.token_timestamps)
    load_s = time.perf_counter() - t0
    audio = load_wav(a.audio)
    with Timer() as tm:
        if a.chunking == "vad":
            segs = silero_segments(audio, os.path.join(a.models, "silero_vad.onnx"), max_speech=28.0)
        else:
            segs = fixed_chunks(len(audio) / SR, 30.0)
        out = []
        for s0, s1 in segs:
            st = rec.create_stream()
            st.accept_waveform(SR, audio[int(s0 * SR):int(s1 * SR)])
            rec.decode_stream(st)
            r = st.result
            ts = list(r.timestamps) if a.token_timestamps else []
            toks = tokens_from_starts(list(r.tokens), ts, s0, s1) if ts else []
            out.append({"start": round(s0, 3), "end": round(s1, 3), "text": r.text, "event": None,
                        "tokens": toks})
    write_result(a.out, f"sherpa_whisper_{v}_{a.chunking}", f"sherpa-onnx-whisper-{v} int8", a.audio,
                 len(audio) / SR, load_s, tm.s, out,
                 {"threads": a.threads, "chunking": a.chunking, "token_timestamps": a.token_timestamps})


if __name__ == "__main__":
    main()
