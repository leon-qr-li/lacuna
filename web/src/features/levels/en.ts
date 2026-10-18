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
  "{name}：": "{name}: ",
  "LACUNA 已自动修好 {n} 处短促破音。": {
    one: "LACUNA repaired {n} short clipped spot automatically. ",
    other: "LACUNA repaired {n} short clipped spots automatically. ",
  },
  "{n} 处较长的破音没有修（修了反而失真）。": {
    one: "{n} longer clipped spot was left alone (repairing it would distort the sound).",
    other: "{n} longer clipped spots were left alone (repairing them would distort the sound).",
  },
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
};
