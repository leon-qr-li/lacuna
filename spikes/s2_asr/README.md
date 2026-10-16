# Spike S2 — local Chinese verbatim ASR comparison

Goal: pick the ASR stack for LACUNA that keeps **verbatim** Mandarin (fillers 嗯/呃/啊/那个/就是,
false starts, repetitions, half phrases) with **char/word timestamps accurate enough to cut audio**.
Results and recommendation: [`REPORT.md`](REPORT.md).

## Files

| file | what |
|---|---|
| `common.py` | shared: WAV loading, Silero VAD segmentation (sherpa-onnx), timing / peak-RSS, JSON schema |
| `run_paraformer.py` | FunASR Paraformer-large zh (vad-punc variant, CIF char timestamps) via sherpa-onnx int8; `--punct` adds CT-Transformer punctuation |
| `run_sensevoice.py` | SenseVoice-Small via sherpa-onnx int8; token timestamps + utterance event/emotion tags; `--itn` for punctuation/ITN |
| `run_faster_whisper.py` | faster-whisper (CTranslate2) with `word_timestamps=True`; `--vad`, `--prompt fillers`, `--compute-type` |
| `run_sherpa_whisper.py` | Whisper turbo/large-v3 ONNX via sherpa-onnx (text only here; the published ONNX lacks cross-attention outputs, so no token timestamps) |
| `convert_sherpa_whisper_to_ct2.py` | **spike-only workaround**: rebuild a faster-whisper model dir from the sherpa-onnx int8 ONNX export because Hugging Face was blocked in the spike container |
| `compare.py` | all evaluation: filler/repetition counts, pairwise disagreement, 60 s consensus-reference recall, timestamps vs energy, silence/bleed behaviour |
| `summarize_full.py` | throughput / RAM / SenseVoice event-tag summary of full-track runs → `out/fulltrack_summary.json` |
| `reference_leon_60s.json` | best-effort consensus reference for Leon 240–300 s of the excerpt (not human-verified) |
| `run_all.sh` | reproduces every run in REPORT.md |
| `out/*.json` | engine outputs (text + timestamps only, no audio) and `summary.json` |

Output JSON schema is documented at the top of `common.py`.

## Reproduce (Linux/macOS, CPU)

```bash
S2=~/lacuna-s2            # scratch dir, OUTSIDE the git repo (audio + models live here)
mkdir -p $S2/audio $S2/models
python3 -m venv $S2/venv
$S2/venv/bin/pip install sherpa-onnx soundfile numpy faster-whisper rapidfuzz
# for the conversion workaround only:
$S2/venv/bin/pip install onnx tiktoken transformers   # no torch needed

# 16 kHz mono excerpts (900–1200 s) — inputs are read-only
for T in Leon Pei; do
  ffmpeg -ss 900 -t 300 -i "原始双轨_$T.wav" -ac 1 -ar 16000 -c:a pcm_s16le $S2/audio/${T}_900_1200.wav
done

# models (GitHub release assets of k2-fsa/sherpa-onnx)
B=https://github.com/k2-fsa/sherpa-onnx/releases/download
cd $S2/models
curl -LO $B/asr-models/silero_vad.onnx
for a in asr-models/sherpa-onnx-paraformer-zh-2023-09-14.tar.bz2 \
         asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2 \
         punctuation-models/sherpa-onnx-punct-ct-transformer-zh-en-vocab272727-2024-04-12-int8.tar.bz2 \
         asr-models/sherpa-onnx-whisper-turbo.tar.bz2 asr-models/sherpa-onnx-whisper-large-v3.tar.bz2; do
  curl -L $B/$a | tar xj
done
```

faster-whisper weights — **normal path** (needs huggingface.co): just pass `--model large-v3` or
`--model large-v3-turbo` to `run_faster_whisper.py`; faster-whisper downloads
`Systran/faster-whisper-large-v3` / `mobiuslabsgmbh/faster-whisper-large-v3-turbo`.

**Spike path** (HF blocked; what REPORT.md numbers use):

```bash
pip download --no-deps openai-whisper -d $S2/dl_whisper && tar xzf $S2/dl_whisper/openai_whisper-*.tar.gz -C $S2/dl_whisper
python convert_sherpa_whisper_to_ct2.py --onnx-dir $S2/models/sherpa-onnx-whisper-turbo --variant turbo \
   --whisper-src $S2/dl_whisper/openai_whisper-20250625 --out $S2/models/ct2-turbo
python convert_sherpa_whisper_to_ct2.py --onnx-dir $S2/models/sherpa-onnx-whisper-large-v3 --variant large-v3 \
   --whisper-src $S2/dl_whisper/openai_whisper-20250625 --out $S2/models/ct2-large-v3
```

Then:

```bash
S2=$S2 ./run_all.sh
$S2/venv/bin/python compare.py --runs $S2/out --audio-dir $S2/audio
```

## Per-engine setup on the target hardware profiles

Sources are the official READMEs as published on PyPI (fetched 2026-10-16) — links below.

### sherpa-onnx (Paraformer, SenseVoice, Silero VAD, CT-punc) — recommended runtime

- Docs: <https://k2-fsa.github.io/sherpa/onnx/> · PyPI: <https://pypi.org/project/sherpa-onnx/> ·
  models: <https://github.com/k2-fsa/sherpa-onnx/releases/tag/asr-models>
- Pre-built wheels for Windows x64, macOS (x64 + arm64) and Linux; pure ONNX Runtime, **no PyTorch**.
  The same int8 model files run on all three OSes — the main reason it suits `cpu-only` and
  `apple-silicon`.
- `cpu-only`: `pip install sherpa-onnx`. Measured here: RTF ≈ 0.11–0.12 on 4 vCPU (see REPORT).
- `cuda-6gb`: sherpa-onnx publishes CUDA-enabled builds (`provider="cuda"`); see the install page
  <https://k2-fsa.github.io/sherpa/onnx/python/install.html> for the CUDA wheel index. Not tested
  here (no GPU). Because CPU RTF is already ~0.1, GPU is optional for these models.
- `apple-silicon`: arm64 wheel; ONNX Runtime CPU (optionally `provider="coreml"`). Not tested here.

### FunASR (native PyTorch; same Paraformer/SenseVoice weights)

- <https://github.com/modelscope/FunASR> · PyPI: <https://pypi.org/project/funasr/>
- Official install: install PyTorch + torchaudio first (CUDA wheel matching the driver for GPU,
  default PyPI wheels for CPU), then `pip install funasr`; use `device="cuda"` only when
  `torch.cuda.is_available()` is True. Models are fetched from ModelScope / Hugging Face
  (`paraformer-zh`, `iic/SenseVoiceSmall`, `fsmn-vad`, `ct-punc`).
- FunASR native Paraformer returns per-char **start and end** times (`timestamp` field), unlike the
  sherpa-onnx port which only exposes per-token start times. Worth re-checking on Leon's machine.
- Also documented: a llama.cpp/GGUF runtime (`llama-funasr-sensevoice`) with Windows CUDA and
  Vulkan zips (the CUDA zip targets sm_86; the 1660 SUPER is sm_75 → use the **Vulkan** package),
  and macOS/Linux builds.
- **Not run in this spike**: modelscope.cn and huggingface.co were blocked by the container proxy,
  so the native checkpoints could not be downloaded. Weights are equivalent to the sherpa-onnx
  exports used (int8 quantisation aside).

### faster-whisper (CTranslate2)

- <https://github.com/SYSTRAN/faster-whisper> · PyPI: <https://pypi.org/project/faster-whisper/> ·
  CTranslate2: <https://opennmt.net/CTranslate2/>
- Windows + CUDA (`cuda-6gb`): requires **cuBLAS for CUDA 12 and cuDNN 9** (latest ctranslate2 supports
  only CUDA 12 / cuDNN 9). On Windows the README points to Purfview's
  [whisper-standalone-win libs archive](https://github.com/Purfview/whisper-standalone-win/releases/tag/libs)
  (unzip into a dir on `PATH`), or `pip install nvidia-cublas-cu12 nvidia-cudnn-cu12==9.*`.
  Use `compute_type="int8_float16"` (README example) — fits 6 GB for large-v3; README benchmark:
  large-v2 int8 beam 5 used 2926 MB VRAM on an RTX 3070 Ti.
- `apple-silicon`: CTranslate2 has **no Metal/GPU backend on macOS**; it runs on CPU (AArch64 with
  Apple Accelerate / Ruy backends per the CTranslate2 README). For GPU on Apple Silicon use
  `mlx-whisper` (<https://pypi.org/project/mlx-whisper/>, supports `word_timestamps=True`) or whisper.cpp
  (Metal).
- `cpu-only`: `compute_type="int8"`.

### whisper.cpp

- <https://github.com/ggml-org/whisper.cpp>; Python binding `pywhispercpp`
  (<https://pypi.org/project/pywhispercpp/>): build flags `GGML_CUDA=1`, `WHISPER_COREML=1`, `GGML_VULKAN=1`;
  Metal is used by default on Apple Silicon builds.
- **Not run**: ggml model files are hosted on Hugging Face (blocked). Same weights as faster-whisper,
  so text behaviour is expected to match Whisper's (see REPORT); its token timestamps are weaker than
  faster-whisper's DTW word timestamps unless `--dtw` is configured.

## Network notes (spike container, 2026-10-16)

| host | reachable |
|---|---|
| pypi.org / files.pythonhosted.org | yes |
| github.com release downloads (k2-fsa/sherpa-onnx) | yes |
| huggingface.co, hf-mirror.com | **no** (proxy 403) |
| modelscope.cn | **no** (proxy 403) |
| openaipublic.azureedge.net (OpenAI .pt) | **no** |
| download.pytorch.org | **no** |
