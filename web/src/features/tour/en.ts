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
  "▶ 播放原始录音": "▶ Play the raw recording",
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

  // the two sentences the tour fills in (answered by the server without the AI: lacuna_app/sample.py)
  "把阿乔问演员名字的那两句删掉": "Cut Alex's two lines about the actor's name",
  "说话时片头音乐再小一点": "Make the intro music a bit quieter under the talk",

  // 1
  "先听听没剪过的样子": "First, hear it uncut",

  // 2 review
  "先听，再决定": "Listen first, then decide",
  "保留，还是恢复？": "Keep, or restore?",

  // 3 listen

  // 4 chat

  // 5 cut by hand

  // 6 silence by hand

  // 7 volume
  "一个大声，一个小声": "One loud, one quiet",

  // 8 music

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
  "正在播放…":
    "Playing…",
  "正在确认 3 处…":
    "Confirming 3 cuts…",
  "正在统一音量…":
    "Matching voices…",
  "**MP3** 体积小，适合分享；**WAV** 音质最好。按 **知道了**，LACUNA 替你点 **开始导出**：整集重新合成，再统一响度。要多久看节目长短，长的节目要等几分钟。":
    "**MP3** is small, good for sharing; **WAV** sounds best. Press **OK** and LACUNA clicks **Start export**: the episode is rebuilt and its loudness evened out. How long depends on the length; a long episode takes a few minutes.",
  "按 **知道了**，LACUNA 点 **{label}**，进入下一部分。":
    "Press **OK** and LACUNA clicks **{label}** to go on.",
  "这一部分看完了":
    "That's this part",
  "LACUNA 拿不准的 3 处":
    "The 3 cuts LACUNA wasn't sure of",
  "LACUNA 已经剪完了第一版。大部分改动它有把握，左边只列出它拿不准的 **3 处**，等你过目。停顿、口头禅这些小改动，整集试听时都能听到。":
    "LACUNA has made the first cut. It's sure of most changes; the list on the left holds only the **3** it wasn't sure of, for you to check. The small ones (pauses, filler words) you'll hear when you play the episode.",
  "{a}离麦克风近，比{b}响很多。尺子上白线是原始音量，彩色条是现在，绿线是目标。按 **知道了**，LACUNA 替你点 **统一两人音量**，两人都到绿线。":
    "{a} sat close to the mic and is much louder than {b}. On the meter, the white line is the original level, the colored bar is now, the green line is the target. Press **OK** and LACUNA clicks **Match both voices**: both reach the green line.",
  "写好了：标题、备选标题、简介和 show notes，点一下就能复制，和导出的音频一起贴到播客平台。剪辑再改，时间戳一键更新。":
    "Done: title, alternatives, blurb and show notes, each one click to copy. Paste them on your podcast platform next to the exported audio. If the edit changes, one click updates the times.",
  "删得对就点 **保留**（键盘 K），想留原话就点 **恢复原话**（R）。删除早已生效，你只是确认。这 3 处都删对了：按 **知道了**，LACUNA 一处处点 **保留**。":
    "If the cut is right, click **Keep** (K); to have the words back, **Restore** (R). The cut is already in; you only confirm it. All 3 are right here: press **Got it** and LACUNA clicks **Keep** on each.",
  "原始多长、成品多长、剪掉多少、配乐几处，都在这里。响度统一到 −16 LUFS，真峰值不超过 −1 dBTP，符合 Apple Podcasts、Spotify 等平台的标准，可以直接上传。":
    "Raw length, final length, how much was cut, how much music: all here. Loudness is −16 LUFS with true peaks under −1 dBTP, the standard of Apple Podcasts, Spotify and others, ready to upload.",
  "左边是素材库，示例准备了 3 首 CC0 授权的音乐。按 **知道了**，LACUNA 把第一首放成 **片头**、第二首放成 **片尾**：有人开口时音乐会自动压低。":
    "On the left is the library: 3 CC0 tracks for the sample. Press **OK** and LACUNA puts the first in as the **Intro** and the second as the **Outro**; the music dips by itself when someone talks.",
  "第 1 处：{a}开头把一句话重说了一遍。按 **知道了**，LACUNA 先放 **A · 原话**（删之前），再放 **B · 剪后**（删之后）。":
    "The first: {a} restarts a sentence at the top. Press **OK** and LACUNA plays **A · Original** (before the cut), then **B · Edited** (after it).",
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
  "❚❚ 正在播放":
    "❚❚ Playing",
  "正在播放原始录音…":
    "Playing the raw recording…",
  "这是示例节目开头 30 秒的原始录音：有重说、口头禅、冷场，两人一个大声一个小声。按 **知道了**，LACUNA 替你播放。":
    "These are the first 30 seconds of the sample, as recorded: restarts, filler words, dead air, one host loud and one quiet. Press **OK** and LACUNA plays it.",
  "听完了。教程最后会放剪好的同一段给你对比。":
    "That's the raw take. At the end of the tour you'll hear the same stretch edited.",
  "第一种：直接跟 LACUNA 说":
    "Way 1: just tell LACUNA",
  "这是整集试听：边听边改，有三种剪法。第一种最省事，直接告诉 LACUNA 你想怎么改。虚线框里，{b}想不起演员名字，来回两句，中间还冷场了。按 **知道了**，LACUNA 替你写一句「{text}」并发送。":
    "This is Listen: edit while you listen, three ways. The easiest: tell LACUNA what to change. In the dashed box, {b} can't recall the actor's name: two lines and dead air between. Press **OK** and LACUNA writes \"{text}\" and sends it.",
  "LACUNA 找到了那一段，给了一个改法，还没动你的音频。":
    "LACUNA found that stretch and suggested a change. Your audio isn't touched yet.",
  "批准前，你可以先听一下":
    "Listen before you approve",
  "LACUNA 不会直接改。**▶ 现在** 是原样，**▶ 改后** 是删掉这两句以后。按 **知道了**，LACUNA 先各放一遍，再替你点 **批准**。":
    "LACUNA never changes anything by itself. **▶ Now** is as it is, **▶ After** is without those two lines. Press **OK** and LACUNA plays each once, then clicks **Approve**.",
  "正在播放，听完批准…":
    "Playing, then approving…",
  "批准了：那两句删掉了，时间线上多了一条橙色剪切线。":
    "Approved: the two lines are gone, and there's a new orange cut on the timeline.",
  "第二种：像改文档一样剪":
    "Way 2: edit it like a document",
  "在文字稿里选中一段字、删掉，对应的声音就剪掉了；删过的字显示删除线，点一下就能恢复。{a}说的「等一下，我喝口水」这句不要。按 **知道了**，LACUNA 替你选中这句，点 **删掉这段**。":
    "Select words in the transcript and delete them: the audio goes with them. Deleted words stay struck through; click them to bring them back. {a}'s \"Hold on, let me grab some water\" can go. Press **OK** and LACUNA selects it and clicks **Cut this**.",
  "删掉了：这句变成删除线，时间线上也多了一条剪切线。":
    "Cut: the line is struck through, and the timeline has a new cut.",
  "第三种：没字的地方，在时间线上剪":
    "Way 3: no words? Cut on the timeline",
  "每人一条轨道，**橙色竖线** 是剪切点。喝完水还有一段冷场（虚线框），没有字，文字稿里删不了。平时在轨道上 **按住鼠标** 拖选它，再点 **删掉这段**；咳嗽这种只有一个人的声音，可以 **只静音** 那个人。按 **知道了**，LACUNA 替你剪掉这段冷场。":
    "One track per host; the **orange lines** are cuts. After the water there's dead air (dashed box): no words, so the transcript can't cut it. Normally you **press and drag** across it on the tracks, then click **Cut this**; a sound from one person only, like a cough, you can **mute** for that person alone. Press **OK** and LACUNA cuts the dead air.",
  "正在剪…":
    "Cutting…",
  "剪好了。这三种剪法剪掉的，都能在这里随时恢复。":
    "Done. Whatever you cut, any of the three ways, can be restored here at any time.",
  "配乐的位置和音量，直接说":
    "Music placement and volume: just say it",
  "放好的音乐，想调位置、音量、淡入淡出，直接说就行。用哪首曲子，还是你在素材库里挑。LACUNA 的改动先变成建议，满意再 **采用**。按 **知道了**，LACUNA 替你发一句「{text}」，再点采用。":
    "To move music, change its volume or its fades, just say so. Which track to use is still your pick from the library. LACUNA's change comes as a suggestion; **Apply** it if you like it. Press **OK** and LACUNA sends \"{text}\", then applies it.",
};
