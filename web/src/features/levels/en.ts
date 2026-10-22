import type { Dict } from "../../i18n";

export const en: Dict = {
  "声音": "Volume",
  "没调成：{message}": "Couldn't change it: {message}",
  "两人音量已统一": "Both hosts evened out",
  "声音页打不开：": "Can't open the Volume page: ",
  "正在测量两人的音量…": "Measuring both hosts' volume…",
  "两人的音量": "The hosts' volume",
  "两人已经一样响（都在 {target} LUFS 左右），审阅和导出听到的是同一个平衡。":
    "Both hosts are equally loud (around {target} LUFS); review and export hear the same balance.",
  "两人现在相差约 {d} dB。点「统一两人音量」，两人都拉到 {target} LUFS。":
    "The hosts are about {d} dB apart. Click “Even out both hosts” to bring both to {target} LUFS.",
  "重新统一": "Even out again",
  "统一两人音量": "Even out both hosts",
  "正在统一…": "Evening out…",
  "也可以在「整集试听」里直接对 AI 制作人说「我的声音太低」「{name} 小一点 3 dB」「音量统一一下」。每次调整都能撤销。":
    "You can also tell the AI producer in Full listen “my voice is too quiet”, “{name} 3 dB lower” or “even out the levels”. Every change can be undone.",
  "破音": "Clipping",
  "原始录音里声音过载被削平的地方（破音），LACUNA 会自动修好：审阅、试听和导出听到的都是修好的声音，原始录音不动。":
    "Where the raw recording overloaded and its peaks were flattened (clipping), LACUNA repairs it automatically: review, listening and export all hear the repaired sound, and the original recording is left untouched.",
  "{name}：{n} 处，已自动修复 {r} 处": {
    one: "{name}: {n} spot, {r} repaired automatically",
    other: "{name}: {n} spots, {r} repaired automatically",
  },
  "{n} 处太严重，硬修反而更难听，保持原样；点时间可以从前 2 秒开始听：": {
    one: "{n} spot is too severe to repair without making it sound worse, so it stays as recorded; click to listen from 2 s before:",
    other: "{n} spots are too severe to repair without making them sound worse, so they stay as recorded; click to listen from 2 s before:",
  },
  "（只列出前 {n} 处）": "(first {n} listed)",
  "下次录音时把这条音轨的输入音量调低一点，就不会再破音。": "Next time, record this track with the input level a little lower and it won't clip.",
  "导出时还会对整集做一次响度标准化（−16 LUFS）和轻压缩；这里调的是两人之间的平衡，以及审阅时听到的音量。":
    "Export still normalises the whole episode (−16 LUFS) with light compression; here you set the balance between the hosts and the volume you hear while reviewing.",
  "现在 {lufs} LUFS": "Now {lufs} LUFS",
  "听不到声音": "Silent",
  "原始 {lufs} LUFS": "raw {lufs} LUFS",
  "{name} 小 1 dB": "{name} 1 dB quieter",
  "{name} 的增益": "{name} gain",
  "{name} 大 1 dB": "{name} 1 dB louder",
  "用建议值 {db}": "Use suggested {db}",
  "最响的地方会被轻轻压住": "The loudest peaks will be gently limited",
  "已自动调平 {db} dB，和人声相称；「音量（dB）」是在这之上的微调。":
    "Levelled automatically by {db} dB to sit with the voices; “Volume (dB)” fine-tunes on top of that.",
  "没有破音": "No clipping",
  "对比这里：原始 / 调整后": "Compare here: original / adjusted",
  "调整后": "Adjusted",
  "−30 轻": "−30 quiet",
  "目标 {n}": "target {n}",
  "响 −6 LUFS": "loud −6 LUFS",
  "调整前 → 调整后": "Before → after",
  "音量": "Volume",
  "✓ 就是建议值": "✓ At the suggested value",
};
