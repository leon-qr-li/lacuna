# Hardware Profile & Hardware-aware Architecture

_Status: CONSTRAINT（硬约束）· Recorded 2026-10-16 from Leon · 所有工程设计必须满足本文件_

## 1. 目标机器

### Primary — Leon（Windows）
| 项 | 规格 | 设计含义 |
|---|---|---|
| OS | Windows 11 Home | 无 Hyper-V/组策略等 Pro 功能；不依赖 WSL；原生 Windows 路径与权限 |
| CPU | AMD Ryzen 5 3600，6C/12T，Zen 2，AVX2，无 AVX-512 | CPU 回退可用但不快；并行度上限按 6 物理核设计 |
| GPU | NVIDIA GTX 1660 SUPER，**6GB VRAM**，Turing TU116，CC 7.5，**无 Tensor Core** | CUDA 可用；FP16 吞吐有限，优先 **int8 / int8_float16** 量化；同一时间只允许 1 个 GPU 模型常驻 |
| RAM | **16GB** DDR4-3200 | 整个 LACUNA（后端 + 模型 + 浏览器）工作集目标 **≤ 6GB**，给系统和浏览器留余量；禁止整集 48kHz float 全量载入内存 |
| Storage | ~500GB SSD | 每集工作集（原始 + 代理 + 缓存）目标 ≤ 10GB，缓存可清理、有上限 |
| Motherboard | Gigabyte B550 UD AC | 无特殊约束 |

### Secondary — 搭档（macOS）
型号未知（待确认 Apple Silicon 还是 Intel、内存大小）。默认按 **Apple Silicon 8–16GB 统一内存** 设计；Intel Mac 走 CPU-only 档位。

## 2. 硬件分档（启动时自动探测，可在 Settings 手动覆盖）

| Profile | 判定 | ASR 后端 | 并发 | 说明 |
|---|---|---|---|---|
| `cuda-6gb` | NVIDIA，VRAM 4–8GB | GPU，int8/int8_float16 量化 | GPU 任务串行；CPU 分析 ≤ 4 worker | Leon 的机器 |
| `cuda-large` | NVIDIA，VRAM > 8GB | GPU，float16 | 同上 | 预留 |
| `apple-silicon` | arm64 macOS | Metal/MLX 或 CPU（按 S2/S6 实测择优） | 统一内存，按总内存缩放 | 搭档可能的机器 |
| `cpu-only` | 无可用 GPU | 小模型 / 高效中文模型 CPU 推理 | ≤ 物理核数 − 2 | 兜底，必须可用，只是更慢 |

探测内容：OS/架构、CPU 核数与指令集、GPU 型号与可用 VRAM、总内存与可用内存、磁盘剩余空间、FFmpeg 可用性。结果写入项目 Diagnostics 页，显示 `Ready / Limited / Unavailable`。

## 3. 各任务在这套硬件上的可行性评估（2026-10-16，待 S2/S6 实测校准）

| 任务 | 评估 | 方案 |
|---|---|---|
| **中文语音转写（ASR）** | ✅ 可行。6GB 足以放下量化后的大模型或中文专用模型 | 候选：FunASR Paraformer-zh / SenseVoice（中文专用、体积小、CPU 也快）、Whisper large-v3 / turbo（faster-whisper int8）。**选型标准是口误与填充词保留率和时间戳精度，其次才是速度**。两轨分别转写，VAD 先去掉对方说话时的静音段，实际计算量远小于 2×2h |
| **Speaker Diarization** | ✅ **基本不需要** | Riverside 分轨已经是“一人一轨”，说话人天然已知。只做每轨 VAD + 串音（bleed）检测，不跑 pyannote 这类重型 diarization 模型，省下大量显存和时间 |
| **音频对齐** | ✅ 可行，CPU 即可 | 两轨对齐与漂移检测用 16kHz 包络互相关；ASR 字级时间戳 + 能量谷精修剪辑点 |
| **声学特征（停顿/语速/能量/音高/笑声）** | ✅ CPU 可行 | 16kHz 单声道分块处理；笑声等事件检测选轻量模型（SenseVoice 自带事件标签是候选） |
| **AI 辅助剪辑决策** | ✅ 不占本地资源 | Claude Opus 5.5 通过 API 运行（Max 自带额度），本地只发文本和数值特征 |
| **FFmpeg 渲染** | ✅ CPU 足够 | 分段渲染（3–8 分钟一段）+ 缓存；局部预览只渲染 ±10–20 秒上下文，目标秒级返回；整集母带只在导出时渲染 |

## 4. 资源管理规则（实现必须遵守）

1. **内存**：分析统一用 16kHz mono 代理文件，分块流式处理；48kHz 原始文件只在渲染时按区间 seek 读取。2h × 2 轨 48kHz float32 约 2.8GB，禁止整体载入。
2. **显存**：一次只加载一个 GPU 模型，用完显式释放；OOM 时自动降级到更小 batch → 更小模型 → CPU，并记录到 Diagnostics。
3. **任务调度**：GPU 任务队列长度 1；CPU 重任务并发上限按档位；前台交互（预览渲染、播放）优先于后台长任务。
4. **磁盘**：缓存有上限与 LRU 清理；原始文件只读，永不删除。
5. **可恢复**：长任务分块落盘，崩溃 / 重启后从最后完成的块继续。
6. **本地模型下载**：首次运行按档位只下载需要的模型，显示大小与进度。

## 5. 待实测项（S2 / S6）
- 各 ASR 候选在 GTX 1660 SUPER 与 Ryzen 5 3600 CPU 上的实时率、显存峰值、内存峰值。
- 整集（2h 双轨）端到端分析耗时，目标：机器时间 ≤ 60 分钟，期间你无需守着。
- 局部预览渲染延迟（目标 < 3 秒）。
- Leon 本机跑一次基准脚本（由我提供，一条命令）。
