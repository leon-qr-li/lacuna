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
  "手动删除": "Cut by hand",
  "手动静音": "Silence by hand",

  // the two sentences the tour fills in (answered by the server without the AI: lacuna_app/sample.py)
  "把阿乔问演员名字的那两句删掉": "Cut Alex's two lines about the actor's name",
  "说话时片头音乐再小一点": "Make the intro music a bit quieter under the talk",

  // 1
  "先听听没剪过的样子": "First, hear it uncut",
  "这是示例节目开头 30 秒的原始录音：有重说、口头禅、冷场，两人一个大声一个小声。教程最后会放剪好的同一段给你对比。":
    "These are the first 30 seconds of the sample, as recorded: restarts, fillers, dead air, one host loud and one quiet. At the end of the tour you'll hear the same stretch edited.",

  // 2 review
  "先看左边的清单": "Start with the list on the left",
  "LACUNA 剪第一刀时，把 **3 处**拿不准、可能删错内容的地方挑出来，排在这里等你过目。现在选中的是第 1 处。":
    "In the first cut, LACUNA picked out **3 edits** it wasn't sure about, ones that might remove real content, and lists them here for you to check. The first one is selected.",
  "先听，再决定": "Listen first, then decide",
  "保留，还是恢复？": "Keep, or restore?",
  "还有 2 处是自动剪的": "2 more were cut automatically",
  "一个口头禅、一段冷场，LACUNA 直接剪好了，不用一处处看。剪得不对也能恢复，下一章就教你。":
    "A filler word and a stretch of dead air: LACUNA just cut them, so you don't have to check each one. You can still restore them; the next chapter shows how.",

  // 3 listen
  "每人一条轨道，波形就是说话的声音。**橙色竖线**是剪切点，这一集只有 5 处。按播放会从头放剪好的版本。":
    "One track per host; the waveform is their voice. The **orange lines** are cuts, only 5 in this episode. Play starts the edited version from the top.",
  "自动剪的，也能恢复": "Automatic cuts can be restored too",

  // 4 chat
  "这两句有点拖": "These two lines drag",
  "{b}想不起演员名字，来回两句，中间还冷场了。这种地方，直接跟 LACUNA 说就能剪。":
    "{b} can't remember the actor's name: two lines with dead air between them. For a spot like this, just tell LACUNA.",
  "用一句话让 LACUNA 剪": "One sentence, and LACUNA cuts it",
  "平时你在这里打字。示例里已经替你填好：「{text}」。**@ 时间** 表示说的是播放头这里。":
    "You'd normally type here. In the sample it's filled in for you: \"{text}\". **@ time** means you're talking about where the playhead is.",
  "先听，再批准": "Listen, then approve",
  "满意就批准": "Approve it if it sounds right",

  // 5 cut by hand
  "自己动手删一段": "Cut a stretch yourself",
  "LACUNA 替你点了菜单里的 **删掉这段**，这句已经删掉了。删错了按 Ctrl + Z 撤销。":
    "LACUNA clicked **Cut this** in the menu for you; the line is gone. Press Ctrl + Z to undo.",

  // 6 silence by hand
  "{b}说话时，{a}咳了一声": "{a} coughs while {b} talks",
  "只静音一个人": "Silence one host only",
  "斜线 = 只删了一个人": "Stripes = one host only",
  "{a}的轨道上出现斜线，表示这里只静音了{a}。把鼠标移上去也能恢复。": "The stripes on {a}'s track show that only {a} was silenced here. Point at them to restore it.",

  // 7 volume
  "一个大声，一个小声": "One loud, one quiet",
  "看这把尺子": "Look at this meter",
  "白线是原始音量，彩色条是现在，绿线是目标。统一后两人的彩色条都到了绿线，右边的波形也一样高了。":
    "The white mark is the original loudness, the coloured bar is now, the green line is the target. After evening out, both bars reach the green line and the waveforms on the right are the same height.",

  // 8 music
  "放上片头": "Add an intro",
  "再放片尾": "Now an outro",
  "这条线是音乐的音量": "This line is the music's volume",
  "点开片头卡片，就能看到：淡入 → 开头只放音乐 → 有人开口时自动压低 → 最后淡出。底下的色块是有人说话的地方。":
    "Open the intro card to see it: fade in → music alone at the start → lowered automatically when someone talks → fade out. The shaded band is where someone is talking.",
  "说一句，让 LACUNA 调": "Say it, and LACUNA adjusts it",
  "采用，还是不要": "Adopt it, or not",

  // 9 export
  "这一集的结果": "This episode, in numbers",
  "右边是这一集的结果：原始多长、成品多长、剪掉多少、配乐几处、两人音量是否已统一。":
    "On the right: how long the recording was and the final episode is, how much was cut, how many music pieces, and whether both hosts are evened out.",
  "响度统一到 −16 LUFS，真峰值不超过 −1 dBTP，这是 Apple Podcasts、Spotify 等平台的标准，可以直接上传。":
    "Loudness at −16 LUFS with true peaks under −1 dBTP: the standard of Apple Podcasts, Spotify and others, so it's ready to upload.",
  "LACUNA 不会直接改，先给你听：**▶ 现在** 是原样，**▶ 改后** 是删掉这两句以后。":
    "LACUNA doesn't change anything yet; first you hear it: **▶ Now** is as it is, **▶ After** is without those two lines.",
  "LACUNA 先放 **A · 原话**（删之前），再放 **B · 剪后**（删之后）。平时你自己点这两个按钮对比。":
    "LACUNA plays **A · Original** (before the cut), then **B · Edited** (after it). Normally you click these two to compare.",
  "LACUNA 按标题和简介画了几版方形封面，挑一张就能用；不满意，说一句话让它改。示例就到这里，最后听一下前后对比。":
    "LACUNA drew a few square covers from the title and blurb. Pick one, or say a sentence to change it. That's the sample; last, hear the before and after.",
  "LACUNA 替你点了 **发送**，看它怎么回答。":
    "LACUNA clicked **Send** for you. Here is its answer.",
  "LACUNA 替你点了 **开始导出**：整集重新合成，再统一响度。要多久看节目长短，长的节目要等几分钟，进度条走完就好。":
    "LACUNA clicked **Start export** for you: the whole episode is rebuilt and its loudness evened out. How long depends on the length; a long episode takes a few minutes. It's ready when the bar is full.",
  "LACUNA 替你点了 **批准**，{b}这两句删掉了。不满意的话，平时可以点「再改」接着说。":
    "LACUNA clicked **Approve** for you, and {b}'s two lines are gone. If you're not happy, click \"Change it\" and keep talking.",
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
  "LACUNA 点开第一首的 **放到 ▾**，选了 **片头**。":
    "LACUNA opened **Use as ▾** on the first track and picked **Intro**.",
  "LACUNA 的改动先变成建议，可以点 **试听**。满意就点 **采用**，片头卡片上的曲线会跟着变；不满意就点「不要」。这次替你点了采用。":
    "LACUNA's change arrives as a suggestion you can **Preview**. Click **Use it** and the intro card's curve follows; click \"Discard\" if not. This time it was used for you.",
  "LACUNA 读剪好的文字稿，写好了这一集的标题、几个备选标题和一句话简介，点一下就能复制。":
    "LACUNA read the edited transcript and wrote the episode title, a few alternatives and a one-line blurb. One click copies them.",
  "Show notes 和章节":
    "Show notes and chapters",
  "Show notes 带时间戳，按话题分好段，和导出的音频一起贴到播客平台就行。剪辑再改，时间戳一键更新。":
    "Show notes come with timestamps, split by topic. Paste them on your podcast platform next to the exported audio. If the edit changes, one click updates the times.",
  "{a}离麦克风近，比{b}响很多。LACUNA 替你点了 **统一两人音量**，把两人都调到同一个响度。":
    "{a} sat close to the mic and is much louder than {b}. LACUNA clicked **Match both voices** for you, bringing both to the same loudness.",
  "{a}说「等一下，我喝口水」，这句不要。平时在轨道上 **按住鼠标** 从左拖到右选中它；这次 LACUNA 替你选好了。":
    "{a} says \"Hold on, let me grab some water\"; that line can go. Normally you **press and drag** across it on the tracks; this time LACUNA selected it for you.",
  "不想自己调数值，也可以直接说。LACUNA 替你发了一句：「{text}」。":
    "Rather than set numbers yourself, just say it. LACUNA sent this for you: \"{text}\".",
  "删得对就点 **保留**（键盘 K）；想留原话就点 **恢复原话**（R）。删除早已生效，你只是确认。这 3 处 LACUNA 都删对了，它替你一处处点了 **保留**。":
    "If the cut is right, click **Keep** (K); to have the words back, click **Restore** (R). The cut is already in; you only confirm it. All 3 cuts are right here, so LACUNA clicked **Keep** on each.",
  "删掉整段会把{b}的话也删了。LACUNA 先选中咳嗽那一小段（橙色虚线框）。":
    "Cutting the whole stretch would cut {b}'s words too. LACUNA first selects just the cough (the dashed orange box).",
  "标题和简介":
    "Title and blurb",
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
  "正在放片头…":
    "Adding the intro…",
  "正在放片尾…":
    "Adding the outro…",
  "正在确认 3 处…":
    "Confirming 3 cuts…",
  "正在统一音量…":
    "Matching voices…",
  "正在选中…":
    "Selecting…",
  "正在采用…":
    "Using it…",
  "正在静音…":
    "Muting…",
  "第二首放到 **片尾**。":
    "The second track goes in as the **Outro**.",
  "菜单里有 **只静音 {a}**：{b}的话留着，只把{a}那条轨道的这一下变安静。LACUNA 替你点了它。":
    "The menu has **Mute {a} only**: {b}'s words stay, only {a}'s track goes quiet here. LACUNA clicked it for you.",
  "虚线框里那条橙色竖线，是自动剪掉的口头禅「呃」。平时把鼠标移上去，弹出卡片后点 **恢复**。这次 LACUNA 替你恢复了它。":
    "The orange line in the dashed box is the \"uh\" that was cut automatically. Normally you hover over it and click **Restore** on the card; this time LACUNA restored it for you.",
};
