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
  "原始录音只读，只在 LACUNA 的服务器上处理，不交给第三方；AI 只看文字稿和停顿等数字，拿不到录音。关掉页面不影响进度。":
    "Your recordings stay untouched and are processed only on LACUNA's servers, never shared with third parties. The AI reads the transcript and timing, never the audio. You can close this page.",
  "AI 第一刀（没连上 AI，只收紧了停顿）：{edits} 处改动，{review} 处需要你过目。":
    "First cut (AI not connected, pauses tightened only): {edits} edits, {review} for you to review.",
  这一集说的语言: "Language of this episode",
  "这个节目有 {n} 位主持人，只用了前 {n} 条分轨（每个节目最多 4 位主持人，每人一条）。":
    "This show has {n} hosts, so only the first {n} tracks were used (a show has at most 4 hosts, one track each).",
  "排队中，前面还有 {n} 集": "Waiting in line: {n} ahead",
  回到导入表单: "Back to the import form",
  "正在上传 {id} · {pct}%": "Uploading {id} · {pct}%",
};
