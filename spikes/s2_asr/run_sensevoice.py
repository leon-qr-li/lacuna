"""SenseVoice-Small (FunAudioLLM, sherpa-onnx int8 export) with token timestamps + event tags.

Model: sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17 (= iic/SenseVoiceSmall).
Event/emotion tags (e.g. Laughter, BGM, Applause) are utterance-level in SenseVoice,
so VAD segmentation granularity determines tag granularity.

Usage:
  python run_sensevoice.py --audio X.wav --models MODELS_DIR --out out/sensevoice_X.json [--itn]
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
    ap.add_argument("--model-dir", default="sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--itn", action="store_true", help="inverse text normalization + punctuation")
    ap.add_argument("--language", default="zh")
    a = ap.parse_args()

    md = os.path.join(a.models, a.model_dir)
    t0 = time.perf_counter()
    rec = so.OfflineRecognizer.from_sense_voice(model=os.path.join(md, "model.int8.onnx"),
                                                tokens=os.path.join(md, "tokens.txt"),
                                                num_threads=a.threads, language=a.language,
                                                use_itn=a.itn)
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
            ev = (getattr(r, "event", "") or "").strip("<|>") or None
            emo = (getattr(r, "emotion", "") or "").strip("<|>") or None
            toks = tokens_from_starts(list(r.tokens), list(r.timestamps), s0, s1)
            out.append({"start": round(s0, 3), "end": round(s1, 3), "text": r.text, "event": ev,
                        "emotion": emo, "tokens": toks})
    write_result(a.out, "sensevoice" + ("_itn" if a.itn else ""), a.model_dir, a.audio, len(audio) / SR,
                 load_s, tm.s, out, {"threads": a.threads, "vad": "silero", "use_itn": a.itn})


if __name__ == "__main__":
    main()
