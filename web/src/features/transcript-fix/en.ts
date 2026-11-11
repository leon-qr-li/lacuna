import type { Dict } from "../../i18n";

export const en: Dict = {
  "按节目设置和系统专有名词校对逐字稿里听错的名字（只改文字，不动音频和剪辑）":
    "Fixing mis-heard names in the transcript with the show and system terms (only the text changes, not the audio or the edits)",
  "正在校对专有名词…": "Fixing names…",
  "已按专有名词自动校对 {n} 处：{list}": "Fixed {n} names automatically: {list}",
  "{wrong} → {right}（{count} 处）": "{wrong} → {right} ({count})",
  "、": ", ",
  // 设置 → 系统专有名词
  "系统专有名词": "System terms",
  "所有节目的逐字稿都会按这些词自动校对，比如 ChatGPT。一行一个。": "Every show's transcripts are checked against these names, e.g. ChatGPT. One per line.",
  "只有管理员能修改。": "Only admins can change them.",
  "保存词表": "Save list",
  "已保存，之后打开的剧集会按新词表自动校对。": "Saved. Episodes opened from now on are checked against the new list.",
  "{n} 个词": "{n} terms",
};
