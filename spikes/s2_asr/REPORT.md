# S2 Report — local Chinese verbatim ASR for 《洛城二三事》

_Date: 2026-10-16 · Spike result. A proposed decision is at the end._

## TL;DR

- **Primary engine on every profile: FunASR Paraformer-large zh** (the `vad-punc` checkpoint, which has CIF char timestamps), run through **sherpa-onnx int8**, with **Silero VAD per track**.
  - It kept every disfluency in the 60 s consensus check (10/10).
  - It kept 12× 嗯 in 5 min, where Whisper kept 0–2.
  - It had the best word-onset timing: median +23 ms, 51 % within 50 ms of the energy onset.
  - It ran a whole 73.5-min track in 5.7 min on 4 CPU threads, under 0.8 GB RAM, with no PyTorch.
- **Cross-check: SenseVoice-Small** on the same runtime. Almost as verbatim (10/10, 14× 嗯), slightly better on English code-switching, gives emotion tags. Its laughter tags are too sparse to rely on (11 in 147 min).
- **Whisper is not fit to be the verbatim source.**
  - Turbo dropped all 嗯/呃/啊 on Leon (0 vs 12–16) and kept only 3–4 of the 10 reference disfluencies.
  - large-v3 kept 5/10, or 7/10 with a filler prompt.
  - With VAD on, both dropped every one of Pei's 29 backchannel 嗯.
  - Turbo word onsets are a median 130 ms late: 84 % would clip the word head.
  - Turbo hallucinated a YouTube outro ("请不吝点赞 订阅 转发 打赏支持明镜与点点栏目").
  - Whisper's only real strength here is English and proper-noun spelling (Kansas City, Florida, viral, Obsession). It can be an optional hint pass on `cuda-6gb`.

## 1. Setup and what was actually run

| item | value |
|---|---|
| Input | `原始双轨_Leon.wav` / `原始双轨_Pei.wav`, raw 900–1200 s (5 min each), resampled to 16 kHz mono with ffmpeg into a scratch dir outside the repo. The 60 s check is excerpt 240–300 s (raw 1140–1200 s). The full 73.5-min tracks were also run, for throughput and event tags. |
| Machine | Cloud container: 4 vCPU Intel Xeon @ 2.8 GHz with AVX-512 VNNI, 15 GB RAM, no GPU. Another job used about 1 core during most runs, so timings are roughly ±20 %. |
| Paraformer | `sherpa-onnx-paraformer-zh-2023-09-14` (FunASR `speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404` exported to ONNX int8; exports `us_cif_peak` → per-char **start** times). sherpa-onnx 1.13.8, 4 threads, Silero VAD (threshold 0.5, min silence 0.3 s, pad 0.2 s). Optional CT-Transformer punctuation (`--punct`). |
| SenseVoice | `sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17` (= `iic/SenseVoiceSmall`), `language=zh`, with and without ITN, same VAD. |
| faster-whisper | faster-whisper 1.2.1 / CTranslate2 4.8.3, int8, beam 5, `word_timestamps=True`, `language=zh`. Variants: `vad_filter` on/off, and `initial_prompt="嗯，呃，就是，那个，然后，啊，我觉得，就是说，对对对，"`. Models: large-v3-turbo and large-v3. |
| Not run | FunASR native (PyTorch) and whisper.cpp. modelscope.cn and huggingface.co return proxy 403; sherpa-onnx exports of the same FunASR weights were used instead. |

> **Caveat on the Whisper weights.** huggingface.co and openaipublic.azureedge.net are blocked here, so official faster-whisper models could not be downloaded. `convert_sherpa_whisper_to_ct2.py` rebuilds a CTranslate2 model from the sherpa-onnx int8 ONNX export of the OpenAI weights (dequantize, map to CTranslate2 WhisperSpec; tokenizer and alignment heads from the openai-whisper sdist). Output is coherent and matches sherpa-onnx's own Whisper output on a 60 s check. Side effects: one extra round of int8 quantization noise; inflated peak RAM (fp16 file quantized at load). Whisper quality may be slightly understated; the verbatim behaviour seen (dropping fillers, hallucinated outros) is well known and consistent across both sizes. **Re-run on Leon's machine with official weights:** `run_faster_whisper.py --model large-v3 --device cuda --compute-type int8_float16`.

## 2. Verbatim retention

### 2.1 Filler and repetition counts, 5-min excerpts (`compare.py` §1)

嗯 also counts 恩/唔. 那个 and 就是 are also content words; treat those columns as context.

| run | track | chars | 嗯 | 呃 | 啊 | 哦 | 那个 | 就是 | immediate repeats | hallucinated boiler-plate |
|---|---|---|---|---|---|---|---|---|---|---|
| **paraformer** | Leon | 1235 | **12** | 2 | **16** | 1 | 2 | 24 | **9** | 0 |
| **sensevoice** | Leon | 1201 | **14** | 2 | 12 | 2 | 2 | 24 | 7 | 0 |
| fw large-v3, VAD | Leon | 1195 | 1 | 2 | 7 | 1 | 2 | 25 | 6 | 0 |
| fw large-v3, VAD, filler prompt | Leon | 1208 | 2 | 2 | 7 | 1 | 2 | 25 | 9 | 0 |
| fw turbo, VAD | Leon | 1172 | **0** | 0 | **0** | 0 | 1 | 23 | 4 | "感谢大家" at cut-off end |
| fw turbo, VAD, filler prompt | Leon | 1330 | 0 | 2 | 3 | 0 | 1 | 28 | 11 (partly garbage) | **"请不吝点赞 订阅 转发 打赏支持明镜与点点栏目"** |
| fw turbo, no VAD | Leon | 1203 | 1 | 0 | 3 | 0 | 1 | 24 | 4 | junk in final 80 ms; duplicated phrase |
| **paraformer** | Pei | 213 | **29** | 0 | 1 | 1 | 0 | 1 | 6 | 0 |
| **sensevoice** | Pei | 212 | **29** | 0 | 2 | 0 | 0 | 1 | 5 | 0 |
| fw large-v3, VAD | Pei | 178 | **0** | 0 | 2 | 0 | 0 | 1 | 2 | 0 |
| fw large-v3, no VAD | Pei | 206 | 28 | 0 | 3 | 0 | 0 | 1 | 6 | 0 |
| fw turbo, VAD | Pei | 176 | **0** | 0 | 2 | 0 | 0 | 1 | 1 | 0 |
| fw turbo, no VAD | Pei | 206 | 48 (≥10 look inserted, §5) | 0 | 2 | 0 | 0 | 1 | 7 | 0 |

Repetitions detected on Leon — Paraformer: 不是不是 那那 跑跑 会会 泛泛 愿愿 更更 那个那个 是是; SenseVoice: 不是不是 那那 泛泛 愿愿 更更 那个那个 是是; large-v3: 跑跑 泛泛 就是就是 愿愿 那个那个 是是; turbo: 不是算过不是算过 泛泛 愿愿 更更. (泛泛 and 愿愿 are lexical, not disfluencies.)

Pei's track is mostly **backchannels** (29 嗯 while Leon talks). The Playbook's interjection logic needs these, and Whisper with VAD drops all of them.

### 2.2 60 s consensus check (Leon, excerpt 240–300 s, `reference_leon_60s.json`)

The reference is a **consensus of engines, not a human transcript**. Each of the 10 items appears in ≥2 independent model families. Because the reference leans on Paraformer and SenseVoice, their CER is not evidence of accuracy; item hits are what matter.

| run | D1 更更 | D2 就是说 | D3 哦 | D4 那个那个 | D5 嗯 | D6 在就现在 | D7 就感受 | D8 嗯 | D9 是是 | D10 不是它不是 | recall |
|---|---|---|---|---|---|---|---|---|---|---|---|
| paraformer | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **10/10** |
| sensevoice | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **10/10** |
| fw large-v3 + filler prompt | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✓ | ✓ (as 呃) | ✓ | ✗ | 7/10 |
| fw large-v3 | ✗ | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ | 5/10 |
| fw turbo | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ | ✓ | 4/10 |
| fw turbo + filler prompt | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ | 3/10 |

Typical Whisper drops: "像嗯待会儿" → "像,呃,待会" (large-v3) / "像待会" (turbo); "可以在就现在" → "可以再,现在" (false start gone); "更更internet" → "更internet"; "那个那个hook" → "那个hook" (turbo); "是是符合" → "是符合" (turbo). The filler prompt helped large-v3 (5→7) and hurt turbo (4→3 plus hallucinated outro); one 60 s sample, noise-level evidence.

### 2.3 Side-by-side snippets (excerpt seconds; raw time = +900 s)

**11–24 s** (both FunASR models agree the true start is "不是不是算过")

| engine | text |
|---|---|
| Paraformer | 不是不是算过不是算了就是没去过**那那边**然后我去canastcity我提的特别喜欢南部嘛就是中部南部**啊**我就想再往那边**跑跑啊** |
| SenseVoice | 不是不是算过不是算了就没去过**那那边**然后我去 Kansasas city 我其实特别喜欢南部嘛就是中部南部**啊**我就想再往那边跑吧**嗯** |
| large-v3 | (就是不是)算过,就是没去过那边然后我去Kansas City我特别喜欢南部嘛就是中部南部我就想再往那边跑跑 |
| turbo | 不是算过不是算过就没去过那边然后我去Kansas City我特别喜欢南部就是中部南部我就想再往那边跑步 |

**264–282 s**

| engine | text |
|---|---|
| Paraformer | 看这部电影之前我基本知道就说**那个那个**hook是什么…像**嗯**待会儿可以**在就现在**就可以聊这两个电影的一些**就**感受我是特别喜欢obsession是因为**嗯** |
| SenseVoice | 看这部电影之前我基本知道就是说**那个那个** hook 是什么…像**嗯**待会儿可以**在就现在**就可以聊这两个电影的一些**就**感受我是特别喜欢 ob 是因为**嗯** |
| large-v3 | 看这部电影之前,我基本知道就是说**那个那个**hook是什么…像,呃,待会可以再,现在就可以聊这两个电影的一些感受我是特别喜欢Obsession,是因为,呃 |
| turbo | 我看这部电影之前我基本知道就是说那个hook是什么…像待会可以在现在就可以聊这两个电影的一些就感受我是特别喜欢obsession是因为 |

**298.5–300 s** (excerpt ends mid-speech)

| engine | text |
|---|---|
| Paraformer / SenseVoice / large-v3 | 一个deliver |
| turbo | 一个deliver**感谢大家** |
| turbo + filler prompt | 一个deliver的是**请不吝点赞 订阅 转发 打赏支持明镜与点点栏目** |
| turbo, no VAD | 一个deliver**那我们下车以来的 我可以做一遍的** |

### 2.4 Proper nouns and English code-switching

Model families disagree on 7–13 % of characters (Paraformer vs SenseVoice: 7 %), mostly English and proper nouns.

| spoken (likely) | Paraformer | SenseVoice | Whisper large-v3 |
|---|---|---|---|
| Miami (迈阿密) | 八米 / 迈阿密 | 迈咪 / 迈阿密 | 迈阿密 |
| Kansas City | canast city | Kansasas city | **Kansas City** |
| viral | verue | **viral** | **viral** |
| Obsession (film) | **obsession** | ob / obession | **Obsession** |
| Backrooms (film) | backroom | back rooms | backroom |
| indie movie (Pei) | in d movie | – | **indie movie** |
| 奥德赛 / 蜘蛛侠 / 好莱坞 | ✓ | ✓ | ✓ |

FunASR native Paraformer supports `hotword=` biasing (per FunASR README). Biasing with the episode's film list is the obvious fix; untested.

### 2.5 Event tags

- SenseVoice, full 73.5-min tracks (`out/fulltrack_summary.json`): Leon 558 Speech, **5 Laughter**, 1 Cough; Pei 518 Speech, **6 Laughter**, 2 Breath.
- Tags are per VAD segment, so laughter inside speech is labelled Speech. Paraformer sometimes writes laughter as text ("哈哈").
- **A dedicated acoustic laughter/breath detector is needed.**

## 3. Timestamp accuracy vs signal energy (Leon excerpt)

**Method.** 10 ms frame energy; energy onsets/offsets after ≥200 ms silence (hysteresis floor +15 dB / +8 dB) → 130 onsets, 138 offsets. Match each to nearest token start/end within ±500 ms. Onset error = token start − energy onset (positive = late = clips word head). Valley test: energy at every token start relative to local peak within ±150 ms, vs random times inside speech.

| run | onset median (signed) | onset median abs | onset ≤50 ms | late >30 ms (clips head) | offset median (signed) | starts in ≥10 dB valley |
|---|---|---|---|---|---|---|
| **paraformer** | **+23 ms** | **47 ms** | **51 %** | 46 % | −104 ms† | **46 %** |
| sensevoice | +5 ms | 84 ms | 32 % | **39 %** | −93 ms† | 47 % |
| fw large-v3 | +50 ms | 80 ms | 32 % | 69 % | −140 ms | 33 % |
| fw turbo | **+130 ms** | 140 ms | 7 % | **84 %** | −120 ms | 28 % |
| random times in speech (baseline) | | | | | | 34 % |

† sherpa-onnx Paraformer/SenseVoice expose **start times only**; end times here are synthetic (next token start, capped +0.6 s), so the offset column says nothing about them. FunASR native gives char start+end and should be measured on Leon's machine.

p90 absolute error is 320–410 ms for every engine, mostly breaths, clicks and lip noise.

**Takeaways:** Paraformer starts are the best anchor (46 % in valleys vs 34 % chance). Whisper DTW word times are no better than random relative to valleys; turbo's are systematically late. **No engine is cut-ready**: treat ASR times as candidates and refine each cut to the nearest energy valley / zero-crossing within about ±150 ms, plus padding (confirms Assessment §4.4).

## 4. Speed and memory (measured on this CPU)

RTF = wall ÷ audio, incl. VAD, excl. model load (2–23 s).

| engine | 5-min Leon RTF | 5-min Pei RTF | full 73.5-min track RTF, Leon / Pei | peak RSS | model on disk |
|---|---|---|---|---|---|
| Paraformer int8 | 0.111 | 0.025 | **0.077 / 0.034** (340 s + 152 s) | 0.41 GB (5 min); 0.69–0.74 GB (full file) | 232 MB |
| + CT-punc int8 | 0.124 | – | – | 0.49 GB | +62 MB |
| SenseVoice-Small int8 | 0.119 | 0.030 | 0.097 / 0.060 (427 s + 265 s) | 0.41 GB; 0.74–0.85 GB | 228 MB |
| fw turbo int8, VAD | 0.73 | 0.085 | – | 2.2 GB | 1.6 GB (fp16) |
| fw turbo int8, no VAD | 0.72 | 0.68 | – | 2.2 GB | |
| fw large-v3 int8, VAD | 1.95 | 1.12‡ | – | 4.7–6.2 GB§ | 3.1 GB (fp16) |
| fw large-v3 int8, no VAD | – | 2.56 | – | 6.3 GB§ | |

‡ Probably temperature-fallback re-decodes on short backchannel chunks. § Inflated by load-time quantization; faster-whisper README reports ~2.9 GB VRAM for large-v2 int8.

**Whole-episode extrapolation** (2 h, two tracks, this CPU): Paraformer ~13 min; SenseVoice ~19 min; turbo ~1.6 h; large-v3 ~6 h. Only FunASR models meet the ≤60 min target on CPU.

**Target hardware (estimates, not measured):**
- **Ryzen 5 3600** (Zen 2, AVX2, no VNNI; 1.5× cores, higher clocks): expect 0.7–1.5× the speeds above — Paraformer ~9–20 min per 2 h episode, SenseVoice ~13–27 min.
- **GTX 1660 SUPER 6 GB** (TU116, CC 7.5, 336 GB/s, ~5 TFLOPS FP32): faster-whisper README has large-v2 int8 beam 5 at RTF ≈ 0.076 on RTX 3070 Ti (2.9 GB VRAM). Assume 2.5–4× slower → large-v3 RTF ≈ 0.2–0.3, ~25–45 min per 2 h two-track episode after VAD, ~3 GB VRAM `int8_float16`; fits 6 GB. Turbo probably 2–4× faster. FunASR models don't need the GPU.
- **Apple Silicon:** sherpa-onnx has arm64 wheels; ONNX Runtime int8 uses ARM dot-product. Expect same order of speed (unmeasured). CTranslate2 has no Metal backend; Whisper on Mac = CPU, mlx-whisper, or whisper.cpp Metal.

## 5. Silence, hallucination and bleed

- **Bleed: none measurable in this excerpt.** When Leon is loud and Pei silent, Pei's track sits at −43.3 dB, same as both quiet (−42.8). Reverse: Leon −57.5 vs −56.8 dB. Shared chars in `compare.py` §5 come from genuine echoing.
- **Pei without VAD:** turbo produced 48 嗯; ten fall in 211–217 s where Paraformer hears one; 16 chars timed in frames with no energy → inserted. large-v3 without VAD looked clean on Pei (4 chars in low-energy frames).
- **Leon, turbo without VAD:** duplicated phrase ("痴迷 / 痴迷跟后世"), junk in final 80 ms.
- **With VAD:** Whisper avoids inserted fillers but drops all real backchannels. No Whisper setting gives both verbatim backchannels and no hallucinations.
- **Paraformer / SenseVoice:** no boiler-plate, no loops; 2–3 chars in low-energy frames (boundary rounding).
- **Hallucinated outros** recur at VAD chunk ends with turbo; any Whisper path needs a blocklist plus `no_speech` and `compression_ratio` filters.

## 6. Recommendation per hardware profile

| profile | primary | cross-check / fallback | notes |
|---|---|---|---|
| `cuda-6gb` (Leon) | **Paraformer-large zh via sherpa-onnx int8 on CPU**, Silero VAD per track, one worker per track | SenseVoice-Small second opinion; optional faster-whisper large-v3 `int8_float16` on GPU as **hint-only** pass for English / proper nouns | GPU stays free for other models |
| `apple-silicon` | Paraformer via sherpa-onnx arm64 on CPU | SenseVoice-Small | mlx-whisper for spelling hints if wanted |
| `cpu-only` | Paraformer via sherpa-onnx | SenseVoice only if time allows | No Whisper (~6 h/episode) |

Why sherpa-onnx rather than FunASR native: one `pip install`, no PyTorch; same model files on Windows/macOS/Linux; peak RAM < 1 GB; Silero VAD and CT-punc bundled. FunASR native remains the fallback **if** its char end times or hotword biasing prove better on Leon's machine.

Product implications: (1) ASR text is evidence, not truth — keep both Paraformer and SenseVoice tokens; where they disagree (esp. fillers/repetitions), mark low confidence and prefer retaining. (2) Always refine cut points against the signal. (3) Laughter needs a dedicated detector. (4) Film titles need hotword biasing from show notes.

## 7. Open risks and next steps

1. **No human ground truth.** Leon should spot-check raw 1140–1200 s against `reference_leon_60s.json` (~5 min).
2. **Small sample.** One 5-min excerpt per host; fast overlapping banter and music beds untested.
3. **Whisper weights reconstructed** from int8 ONNX; re-run with official weights on the 1660S. Verbatim conclusion unlikely to flip.
4. **Paraformer end times** not exposed by sherpa-onnx; measure FunASR native or derive ends from next start + energy.
5. **English code-switching / film titles** are Paraformer's weakest area; test hotword biasing; otherwise Whisper or Claude may only suggest spellings, never rewrite fillers.
6. **VAD sensitivity** decides whether soft 嗯 survive; tune per track (Leon ~6 dB quieter; Pei's noise floor ~14 dB higher).
7. **Timing noise** (~1 of 4 vCPUs used by a parallel job); Ryzen/GPU numbers are estimates until benchmarked on Leon's machine.
8. **Licensing:** FunASR toolkit MIT, but Paraformer and SenseVoice weights fall under the FunASR Model Open Source License Agreement — review before bundling. Whisper weights MIT.
9. **Model downloads:** huggingface.co / modelscope.cn blocked here, GitHub release assets (k2-fsa/sherpa-onnx) worked; first-run downloader should support mirrors.

**Proposed decision** (pending Leon's spot-check): "Verbatim ASR = Paraformer-large zh via sherpa-onnx int8 with per-track Silero VAD on all profiles; SenseVoice-Small as cross-check; Whisper only as an optional proper-noun hint pass on cuda-6gb; all cut points refined against the signal."
