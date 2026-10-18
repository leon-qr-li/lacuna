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
  "也可以在「整集试听」里直接对 AI 制作人说「我的声音太低」「Pei 小一点 3 dB」「两人音量统一一下」。每次调整都能撤销。":
    "You can also tell the AI producer in Full listen “my voice is too quiet”, “Pei 3 dB lower” or “even out the hosts”. Every change can be undone.",
  "破音": "Clipping",
  "原始录音里有声音过载被削平的地方（破音）。LACUNA 只标出来，不修补；点时间可以从前 2 秒开始听，听着刺耳可以在审阅里把那句删掉。":
    "The raw recording overloaded in some spots and the peaks were flattened (clipping). LACUNA only marks them and doesn't repair them; click a time to listen from 2 s before, and if it sounds harsh, cut that sentence in review.",
  "{name}：{n} 处": { one: "{name}: {n} spot", other: "{name}: {n} spots" },
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
};
