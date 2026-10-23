import type { Dict } from "../../i18n";

export const en: Dict = {
  // the engine
  "示例集会回到 LACUNA 第一刀刚做完的样子，你在里面做的改动都会清掉，然后从头开始教程。":
    "The sample episode goes back to just after LACUNA's first cut. Your changes in it are cleared and the tour starts again.",
  "重新开始": "Start again",
  "重新开始示例教程": "Restart the sample tour",
  "示例教程 · 第 {n} 步，共 {total} 步": "Sample tour · step {n} of {total}",
  "第 {n} 步，共 {total} 步": "Step {n} of {total}",
  "继续示例教程": "Continue the sample tour",
  "暂停教程": "Pause the tour",
  "还剩 {n} 步，大约 {m} 分钟": "{n} steps left, about {m} min",
  "走完你就亲手剪好了一集，最后会放剪前剪后的对比给你听。现在离开也没关系，我们记得你走到哪儿，下次打开示例节目接着走。":
    "Finish and you'll have edited a whole episode yourself, with a before / after to hear at the end. Leaving now is fine too: we remember where you are and pick up from there next time you open the sample show.",
  "继续教程": "Keep going",
  "先离开，下次接着走": "Leave for now",
  "⏸ 暂停播放": "⏸ Pause",
  "❚❚ 暂停": "❚❚ Pause",
  "▶ 播放原始录音": "▶ Play the raw recording",
  "听完自动进入下一步。": "The next step starts when it ends.",
  "下一步": "Next",
  "示例节目不占用你的额度。两位主持人的声音是合成的。": "The sample show doesn't use your quota. The two hosts' voices are synthetic.",
  "剪辑 {a} → {b}": "Edited {a} → {b}",
  "成品含配乐 {c}": "Final with music {c}",
  "审阅了 {n} 处": "{n} reviewed",
  "手动剪了 {n} 处": "{n} edited by hand",
  "配乐 {n} 段": "{n} music pieces",
  "示例完成": "Sample done",
  "同一段 30 秒，剪之前和剪之后": "The same 30 seconds, before and after",
  "剪之前": "Before",
  "原始录音 · 0:30": "Raw recording · 0:30",
  "重说 · 口头禅 · 冷场 · 跑题 · 音量一大一小": "Restarts · fillers · dead air · a tangent · one loud, one quiet",
  "剪之后": "After",
  "成品前 30 秒 · 带配乐": "First 30 s of the final mix · with music",
  "紧凑、两人一样大声、对话的节奏和笑声都还在": "Tight, both hosts equally loud, and the rhythm and laughs are still there",
  "再走一遍示例": "Go through the sample again",
  "自己在示例里试试": "Try the sample yourself",
  "示例节目会留在你的节目列表里，可以随便点；不想要了在 设置 → 通用 里删除。":
    "The sample show stays in your list of shows to explore. To remove it, go to Settings → General.",

  // chapters
  "先听原始录音": "The raw recording",
  "对 LACUNA 说": "Ask LACUNA",

  // the two sentences the tour fills in (answered by the server without the AI: lacuna_app/sample.py)
  "把阿乔问演员名字的那两句删掉": "Cut Alex's two lines about the actor's name",
  "说话时片头音乐再小一点": "Make the intro music a bit quieter under the talk",

  // 1
  "先听听没剪过的样子": "First, hear it uncut",
  "这是示例节目开头 30 秒的原始录音：有重说、口头禅、冷场，两人一个大声一个小声。教程最后会放剪好的同一段给你对比。":
    "These are the first 30 seconds of the sample, as recorded: restarts, fillers, dead air, one host loud and one quiet. At the end of the tour you'll hear the same stretch edited.",

  // 2 review
  "先听，再决定": "Listen first, then decide",
  "保留，还是恢复？": "Keep, or restore?",

  // 3 listen

  // 4 chat
  "满意就批准": "Approve it if it sounds right",

  // 5 cut by hand
  "自己动手删一段": "Cut a stretch yourself",

  // 6 silence by hand
  "{b}说话时，{a}咳了一声": "{a} coughs while {b} talks",

  // 7 volume
  "一个大声，一个小声": "One loud, one quiet",

  // 8 music
  "说一句，让 LACUNA 调": "Say it, and LACUNA adjusts it",

  // 9 export
  "这一集的结果": "This episode, in numbers",
  "LACUNA 正在写…":
    "LACUNA is writing…",
  "LACUNA 正在回答…":
    "LACUNA is answering…",
  "LACUNA 正在操作…":
    "LACUNA is working…",
  "LACUNA 正在画…":
    "LACUNA is drawing…",
  "LACUNA 正在调…":
    "LACUNA is adjusting…",
  "正在删…":
    "Cutting…",
  "正在导出…":
    "Exporting…",
  "正在恢复…":
    "Restoring…",
  "正在批准…":
    "Approving…",
  "正在播放…":
    "Playing…",
  "正在确认 3 处…":
    "Confirming 3 cuts…",
  "正在统一音量…":
    "Matching voices…",
  "正在静音…":
    "Muting…",
  "**MP3** 体积小，适合分享；**WAV** 音质最好。按 **知道了**，LACUNA 替你点 **开始导出**：整集重新合成，再统一响度。要多久看节目长短，长的节目要等几分钟。":
    "**MP3** is small, good for sharing; **WAV** sounds best. Press **OK** and LACUNA clicks **Start export**: the episode is rebuilt and its loudness evened out. How long depends on the length; a long episode takes a few minutes.",
  "LACUNA 不会直接改。批准前，你可以先听一下：**▶ 现在** 是原样，**▶ 改后** 是删掉这两句以后。按 **知道了**，LACUNA 替你各放一遍。":
    "LACUNA doesn't change anything by itself. Before approving you can listen: **▶ Now** is as it is, **▶ After** is without those two lines. Press **OK** and LACUNA plays each once.",
  "LACUNA 点 **{label}**，进入下一部分。":
    "LACUNA clicks **{label}** to go on.",
  "{a}离麦克风近，比{b}响很多。尺子上白线是原始音量，彩色条是现在，绿线是目标。按 **知道了**，LACUNA 替你点 **统一两人音量**，两人都到绿线。":
    "{a} sat close to the mic and is much louder than {b}. On the meter, the white line is the original level, the colored bar is now, the green line is the target. Press **OK** and LACUNA clicks **Match both voices**: both reach the green line.",
  "{a}说「等一下，我喝口水」（虚线框），这句不要。平时在轨道上 **按住鼠标** 从左拖到右选中它，再点菜单里的 **删掉这段**。按 **知道了**，LACUNA 替你做一遍。":
    "{a} says \"Hold on, let me grab some water\" (dashed box); that line can go. Normally you **press and drag** across it on the tracks, then click **Cut this** in the menu. Press **OK** and LACUNA does it once for you.",
  "不想自己调数值，直接说就行。LACUNA 的改动先变成建议，满意再 **采用**。按 **知道了**，LACUNA 替你发一句「{text}」，再点采用。":
    "Rather than set numbers, just say it. LACUNA's change comes as a suggestion; **Use it** if you like it. Press **OK** and LACUNA sends \"{text}\", then uses the suggestion.",
  "写好了：标题、备选标题、简介和 show notes，点一下就能复制，和导出的音频一起贴到播客平台。剪辑再改，时间戳一键更新。":
    "Done: title, alternatives, blurb and show notes, each one click to copy. Paste them on your podcast platform next to the exported audio. If the edit changes, one click updates the times.",
  "删得对就点 **保留**（键盘 K），想留原话就点 **恢复原话**（R）。删除早已生效，你只是确认。这 3 处都删对了：按 **知道了**，LACUNA 一处处点 **保留**。":
    "If the cut is right, click **Keep** (K); to have the words back, **Restore** (R). The cut is already in; you only confirm it. All 3 are right here: press **Got it** and LACUNA clicks **Keep** on each.",
  "删掉整段会把{b}的话也删了。平时选中咳嗽那一小段（虚线框），点 **只静音 {a}**：{b}的话留着，只有{a}那条轨道变安静。按 **知道了**，LACUNA 替你做一遍。":
    "Cutting the whole stretch would cut {b}'s words too. Normally you select just the cough (dashed box) and click **Mute {a} only**: {b}'s words stay, only {a}'s track goes quiet. Press **OK** and LACUNA does it once for you.",
  "原始多长、成品多长、剪掉多少、配乐几处，都在这里。响度统一到 −16 LUFS，真峰值不超过 −1 dBTP，符合 Apple Podcasts、Spotify 等平台的标准，可以直接上传。":
    "Raw length, final length, how much was cut, how much music: all here. Loudness is −16 LUFS with true peaks under −1 dBTP, the standard of Apple Podcasts, Spotify and others, ready to upload.",
  "左边是素材库，示例准备了 3 首 CC0 授权的音乐。按 **知道了**，LACUNA 把第一首放成 **片头**、第二首放成 **片尾**：有人开口时音乐会自动压低。":
    "On the left is the library: 3 CC0 tracks for the sample. Press **OK** and LACUNA puts the first in as the **Intro** and the second as the **Outro**; the music dips by itself when someone talks.",
  "左边清单里是 LACUNA 拿不准的 **3 处**，等你过目。第 1 处：{a}开头把一句话重说了一遍。按 **知道了**，LACUNA 先放 **A · 原话**（删之前），再放 **B · 剪后**（删之后）。":
    "The list on the left holds the **3 cuts** LACUNA wasn't sure of, for you to check. The first: {a} restarts a sentence at the top. Press **OK** and LACUNA plays **A · Original** (before the cut), then **B · Edited** (after it).",
  "批准前，可以先听":
    "Listen before approving",
  "按 **知道了**，LACUNA 按标题和简介画几版方形封面。":
    "Press **OK** and LACUNA draws a few square covers from the title and blurb.",
  "按 **知道了**，LACUNA 读剪好的文字稿，写这一集的标题、一句话简介和带时间戳的 show notes。":
    "Press **OK** and LACUNA reads the edited transcript and writes the title, a one-line blurb and timestamped show notes.",
  "挑一张就能用；不满意，说一句话让它改。示例就到这里，最后听一下剪前剪后的对比。":
    "Pick one and it's ready; if not, say a sentence to change it. That's the sample; last, hear the before and after.",
  "放上片头和片尾":
    "Add an intro and an outro",
  "正在放音乐…":
    "Adding the music…",
  "每人一条轨道，**橙色竖线** 是剪切点：现在画面里有 {n} 处（整集共 {total} 处）。虚线框里那条剪掉的是口头禅「呃」，自动剪的也能恢复：平时把鼠标移上去点 **恢复**，或者点文字稿里的删除线。按 **知道了**，LACUNA 替你恢复它。":
    "One track per host; the **orange lines** are cuts: {n} in view now ({total} in the episode). The one in the dashed box removed an \"uh\"; automatic cuts can be undone too: hover and click **Restore**, or click the struck-through words. Press **OK** and LACUNA restores it.",
  "满意就点 **批准**；不满意，平时可以点「再改」接着说。按 **知道了**，LACUNA 替你批准。":
    "If you like it, click **Approve**; if not, click \"Change it\" and keep talking. Press **OK** and LACUNA approves it.",
  "直接跟 LACUNA 说":
    "Just tell LACUNA",
  "虚线框里，{b}想不起演员名字，来回两句，中间还冷场了。这种地方直接跟 LACUNA 说就能剪。按 **知道了**，LACUNA 替你写一句「{text}」并发送。":
    "In the dashed box {b} can't recall the actor's name: two lines and a silence. Just tell LACUNA to cut a spot like this. Press **OK** and LACUNA writes \"{text}\" and sends it.",
};
