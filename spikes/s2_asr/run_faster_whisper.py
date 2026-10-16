"""faster-whisper (CTranslate2) with word timestamps.

Usage:
  python run_faster_whisper.py --audio X.wav --model MODEL_DIR_OR_NAME --out out/x.json \
      [--prompt fillers] [--vad] [--compute-type int8] [--beam 5]

--model: a local CT2 dir, or (production) a name such as "large-v3" / "large-v3-turbo"
         that faster-whisper downloads from Hugging Face.
--prompt fillers : initial_prompt "嗯，呃，就是，那个，然后，啊，我觉得，" to bias toward verbatim
--vad            : vad_filter=True (faster-whisper's bundled Silero VAD)
"""
import argparse
import os
import time

from common import SR, Timer, load_wav, write_result

FILLER_PROMPT = "嗯，呃，就是，那个，然后，啊，我觉得，就是说，对对对，"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--prompt", default="none", choices=["none", "fillers"])
    ap.add_argument("--vad", action="store_true")
    ap.add_argument("--compute-type", default="int8")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--beam", type=int, default=5)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--no-condition", action="store_true", help="condition_on_previous_text=False")
    a = ap.parse_args()

    from faster_whisper import WhisperModel

    t0 = time.perf_counter()
    model = WhisperModel(a.model, device=a.device, compute_type=a.compute_type, cpu_threads=a.threads)
    load_s = time.perf_counter() - t0
    audio = load_wav(a.audio)
    prompt = FILLER_PROMPT if a.prompt == "fillers" else None
    with Timer() as tm:
        segs, info = model.transcribe(
            audio, language="zh", task="transcribe", beam_size=a.beam, word_timestamps=True,
            initial_prompt=prompt, vad_filter=a.vad,
            vad_parameters={"min_silence_duration_ms": 500} if a.vad else None,
            condition_on_previous_text=not a.no_condition)
        out = []
        for s in segs:  # generator: decoding happens here
            toks = [{"t": w.word, "start": round(w.start, 3), "end": round(w.end, 3),
                     "p": round(w.probability, 3)} for w in (s.words or [])]
            out.append({"start": round(s.start, 3), "end": round(s.end, 3), "text": s.text, "event": None,
                        "tokens": toks, "no_speech_prob": round(s.no_speech_prob, 3),
                        "avg_logprob": round(s.avg_logprob, 3),
                        "compression_ratio": round(s.compression_ratio, 2)})
    name = os.path.basename(a.model.rstrip("/"))
    tag = f"fw_{name}_{'vad' if a.vad else 'novad'}_{a.prompt}"
    write_result(a.out, tag, name, a.audio, len(audio) / SR, load_s, tm.s, out,
                 {"compute_type": a.compute_type, "device": a.device, "beam": a.beam, "vad_filter": a.vad,
                  "initial_prompt": prompt, "threads": a.threads,
                  "condition_on_previous_text": not a.no_condition})


if __name__ == "__main__":
    main()
