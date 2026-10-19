import type { Dict } from "../../i18n";

export const en: Dict = {
  "识别 {name} 的分轨": "Transcribing {name}'s track",
  "选择 {n} 条分轨": "Choose {n} tracks",
  选择分轨: "Choose the track",
  "选择 {name} 的分轨": "Choose {name}'s track",
  "把 {names} 的分轨拖到这里": "Drag {names}'s tracks here",
  "可以一次拖 {n} 个。文件名里有主持人名字的会自动对上，也可以拖到下面某一条上。":
    "You can drop all {n} at once. Files with a host's name in the file name go to the right track, or drop onto a track below.",
  "{name} 的分轨": "{name}'s track",
  "⇅ 对调 {a} 和 {b}": "⇅ Swap {a} and {b}",
  "正在读入 {name} · {pct}%": "Reading {name} · {pct}%",
  "换一个": "Replace",
  "原始录音只读，不会被改动。逐字识别和分析都在这台电脑上做，只有文字和数字会发给 LACUNA 的 AI 做第一刀。长录音要跑一阵，可以关掉这页，进度不会丢。":
    "The original recordings are read-only. Transcription and analysis run on this computer; only text and numbers go to LACUNA's AI for the first cut. Long recordings take a while: you can close this page without losing progress.",
  "AI 第一刀（没连上 AI，只收紧了停顿）：{edits} 处改动，{review} 处需要你过目。":
    "First cut (AI not connected, pauses tightened only): {edits} edits, {review} for you to review.",
};
