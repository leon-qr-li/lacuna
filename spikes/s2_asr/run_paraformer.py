"""Paraformer-large zh (FunASR weights, sherpa-onnx int8 export) with char timestamps.

Model: sherpa-onnx-paraformer-zh-2023-09-14 = FunASR
  speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404 (ONNX, int8),
  which exports the CIF peaks (us_cif_peak) needed for per-char timestamps.
Segmentation: Silero VAD (sherpa-onnx), 0.2 s padding.

Usage:
  python run_paraformer.py --audio X.wav --models MODELS_DIR --out out/paraformer_X.json [--punct]
"""
import argparse
import os
import time

import sherpa_onnx as so

from common import SR, Timer, load_wav, silero_segments, tokens_from_starts, write_result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True)
    ap.add_argument("--models", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model-dir", default="sherpa-onnx-paraformer-zh-2023-09-14")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--punct", action="store_true", help="add CT-Transformer punctuation (text only)")
    a = ap.parse_args()

    md = os.path.join(a.models, a.model_dir)
    model_file = os.path.join(md, "model.int8.onnx")
    if not os.path.exists(model_file):
        model_file = os.path.join(md, "model.onnx")
    t0 = time.perf_counter()
    rec = so.OfflineRecognizer.from_paraformer(paraformer=model_file, tokens=os.path.join(md, "tokens.txt"),
                                               num_threads=a.threads)
    punct = None
    if a.punct:
        pm = os.path.join(a.models, "sherpa-onnx-punct-ct-transformer-zh-en-vocab272727-2024-04-12-int8")
        cfg = so.OfflinePunctuationConfig(model=so.OfflinePunctuationModelConfig(
            ct_transformer=os.path.join(pm, "model.int8.onnx"), num_threads=a.threads))
        punct = so.OfflinePunctuation(cfg)
    load_s = time.perf_counter() - t0

    audio = load_wav(a.audio)
    with Timer() as tm:
        segs = silero_segments(audio, os.path.join(a.models, "silero_vad.onnx"))
        out = []
        for s0, s1 in segs:
            st = rec.create_stream()
            st.accept_waveform(SR, audio[int(s0 * SR):int(s1 * SR)])
            rec.decode_stream(st)
            r = st.result
            text = r.text
            if punct and text.strip():
                text = punct.add_punctuation(text)
            toks = tokens_from_starts(list(r.tokens), list(r.timestamps), s0, s1,
                                      list(getattr(r, "durations", []) or []))
            out.append({"start": round(s0, 3), "end": round(s1, 3), "text": text, "event": None,
                        "tokens": toks})
    write_result(a.out, "paraformer", a.model_dir, a.audio, len(audio) / SR, load_s, tm.s, out,
                 {"threads": a.threads, "vad": "silero", "punct": bool(a.punct)})


if __name__ == "__main__":
    main()
