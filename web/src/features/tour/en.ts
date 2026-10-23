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
  "跳过这一步": "Skip this step",
  "⏸ 暂停播放": "⏸ Pause",
  "❚❚ 暂停": "❚❚ Pause",
  "▶ 播放原始录音": "▶ Play the raw recording",
  "听完自动进入下一步。": "The next step starts when it ends.",
  "下一步": "Next",
  "示例节目不占用你的额度。两位主持人的声音是合成的。": "The sample show doesn't use your quota. The two hosts' voices are synthetic.",
  "剪辑 {a} → {b}": "Edited {a} → {b}",
  "成品含配乐 {c}": "Final with music {c}",
  "你审阅了 {n} 处": "You reviewed {n}",
  "你动手剪了 {n} 处": "You edited {n} yourself",
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
  "去看看「发布」": "Have a look at Publish",
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
  "这一处删了什么": "What this edit removed",
  "最上面是删了什么、删了多久；下面一行是 LACUNA 删它的理由；再下面是前后文，**删除线**就是被删掉的话。":
    "At the top: what was cut and for how long. Below it, LACUNA's reason. Then the words around it: the **struck-through** words are the ones removed.",
  "先听，再决定": "Listen first, then decide",
  "点 **A · 原话** 听删之前，再点 **B · 剪后** 听删之后。": "Click **A · Original** to hear it before the cut, then **B · cut** to hear it after.",
  "两个都听过会自动继续": "Moves on by itself once you've heard both",
  "嫌慢可以倍速": "Speed it up if you like",
  "点 **1×** 切到 1.5× 听，音调不变。整集试听里也一样。": "Click **1×** to switch to 1.5×; the pitch stays the same. Listen has it too.",
  "保留，还是恢复？": "Keep, or restore?",
  "删得对就点 **保留**（键盘 K）；想留原话就点 **恢复原话**（R）。删除早已生效，你只是确认。后面 2 处也一样：先听 A/B，再决定。":
    "If the cut is right, click **Keep** (K); to have the words back, click **Restore original** (R). The cut is already in place; you're only confirming it. The other 2 work the same way: listen to A/B, then decide.",
  "3 处都决定后继续": "Continues once all 3 are decided",
  "3 处都看完了": "All 3 checked",
  "这里显示看了几处。旁边的 **?** 是全部快捷键。": "This shows how many you've looked at. The **?** next to it lists every shortcut.",
  "处数多时，一键确认": "Many edits? Confirm the rest at once",
  "点 **剩下的全部保留**，没看的那些一次确认：LACUNA 删了的保持删，没删的保持原样。按错了按 **Ctrl+Z** 撤销。这一集只有 3 处，我们一处处来。":
    "Click **Keep all the rest** to confirm all the ones you haven't looked at: what LACUNA cut stays cut, what it left stays. Pressed it by mistake? **Ctrl+Z** undoes it. This episode has only 3, so let's go one by one.",
  "还有 2 处是自动剪的": "2 more were cut automatically",
  "一个口头禅、一段冷场，LACUNA 直接剪好了，不用一处处看。剪得不对也能恢复，下一章就教你。":
    "A filler word and a stretch of dead air: LACUNA just cut them, so you don't have to check each one. You can still restore them; the next chapter shows how.",
  "进入整集试听": "On to Listen",
  "审阅做完了。点右上角 **下一步：整集试听**，从头听一遍整集。": "Reviewing is done. Click **Next: Listen** at the top right to play the whole episode.",
  "点「下一步」": "Click \"Next\"",

  // 3 listen
  "每人一条轨道，波形就是说话的声音。**橙色竖线**是剪切点，这一集只有 5 处。按播放会从头放剪好的版本。":
    "One track per host; the waveform is their voice. The **orange lines** are cuts, only 5 in this episode. Play starts the edited version from the top.",
  "图例": "Legend",
  "剪切点、单轨删减（只删一个人）、已恢复、待批准、你选中的，在时间线上分别长这样。":
    "This is how a cut, a one-track cut (only one host), a restored edit, a pending one and your selection look on the timeline.",
  "播放条": "The player",
  "**−5s / +5s** 前后跳，**1× / 1.5×** 切倍速；勾上 **暂停时回退 5 秒**，每次暂停后会往回退一点，方便重听。空格键也能播放 / 暂停。":
    "**−5s / +5s** jump back and forward, **1× / 1.5×** change the speed; with **Rewind 5 s on pause** on, each pause steps back a little so you can hear it again. Space plays and pauses too.",
  "自动剪的，也能恢复": "Automatic cuts can be restored too",
  "把鼠标移到虚线框里那条橙色竖线上，这是自动剪掉的口头禅「呃」。弹出卡片后先点 **▶ 听前后**，再点 **恢复**。":
    "Move the pointer onto the orange line in the dashed box: the filler \"uh\" that was cut automatically. When its card opens, click **▶ Hear around it**, then **Restore**.",
  "点「恢复」会自动继续": "Moves on by itself once you click \"Restore\"",
  "文字稿跟着变": "The transcript follows",
  "「呃」回来了，删除线也没了。文字稿里任何删除线，点一下也能恢复。":
    "The \"uh\" is back and no longer struck through. Clicking any struck-through words in the transcript restores them too.",
  "点右边的 **这附近改了什么** 标签：播放头附近的改动都列在这里，可以直接 **恢复** 或 **重新应用**。刚才恢复的「呃」也在这里。":
    "Click the **Edits around here** tab on the right: it lists the edits near the playhead, each with **Restore** or **Apply again**. The \"uh\" you just restored is there too.",
  "点开标签后继续": "Continues once the tab is open",

  // 4 chat
  "这两句有点拖": "These two lines drag",
  "{b}想不起演员名字，来回两句，中间还冷场了。这种地方，直接跟 LACUNA 说就能剪。":
    "{b} can't remember the actor's name: two lines with dead air between them. For a spot like this, just tell LACUNA.",
  "用一句话让 LACUNA 剪": "One sentence, and LACUNA cuts it",
  "平时你在这里打字。示例里已经替你填好：「{text}」。**@ 时间** 表示说的是播放头这里。":
    "You'd normally type here. In the sample it's filled in for you: \"{text}\". **@ time** means you're talking about where the playhead is.",
  "也可以用嘴说": "Or just say it",
  "点 🎤 直接说话，不用打字。**记住** 是让 LACUNA 把这句当成以后的规则（比如「笑声别剪」），下一集也照做。":
    "Click 🎤 to speak instead of typing. **Remember** makes the sentence a rule LACUNA keeps (say, \"don't cut laughter\"), in later episodes too.",
  "点 **发送**，看 LACUNA 怎么回答。": "Click **Send** and see what LACUNA says.",
  "发送后继续": "Continues once it's sent",
  "黄色虚线框：待批准": "The yellow dashed box: waiting for you",
  "LACUNA 不会直接改。它要删的地方先在时间线上用黄色虚线框标出来，等你点头。":
    "LACUNA never changes it on its own. What it wants to cut is marked on the timeline with a yellow dashed box until you say yes.",
  "先听，再批准": "Listen, then approve",
  "点 **试听前后对比**，再分别点 **▶ 现在** 和 **▶ 改后** 听一下。": "Click **Before / after**, then play **▶ Now** and **▶ After**.",
  "满意就批准": "Approve it if it sounds right",
  "点 **批准**，这两句就删掉了。不满意的话，平时可以点「再改」接着说。":
    "Click **Approve** and the two lines are gone. If it's not right, you'd click \"Change it\" and say more.",
  "批准后继续": "Continues once it's approved",

  // 5 cut by hand
  "自己动手删一段": "Cut a stretch yourself",
  "{a}说「等一下，我喝口水」，这句不要。LACUNA 已经帮你选中了它。平时自己删：在轨道上 **按住鼠标** 从左拖到右。":
    "{a} says \"Hold on, let me grab some water\"; that line can go. LACUNA has selected it for you. To do it yourself: **press and drag** across it on the tracks.",
  "选中后的菜单": "The selection menu",
  "松开鼠标，选区旁边弹出菜单：**删掉这段**（Ctrl X），或者 **只静音** 其中一个人。空格只放选中的这段，Esc 取消选中；拖选区的边可以调整范围。":
    "When you let go, a menu opens next to the selection: **Cut this** (Ctrl X), or **Silence** one host only. Space plays just the selection, Esc drops it, and dragging its edges adjusts it.",
  "LACUNA 替你点了菜单里的 **删掉这段**，这句已经删掉了。删错了按 Ctrl + Z 撤销。":
    "LACUNA clicked **Cut this** in the menu for you; the line is gone. Press Ctrl + Z to undo.",
  "拖选后继续": "Continues once it's selected",
  "在文字稿里删，更快": "Faster: cut in the transcript",
  "不想在波形上找，就在文字稿里 **选中文字**（可以只选一个词），下面会出现工具条：**删掉这段**、**只静音** 某人、**▶ 听选中**、**取消**。删过的字显示删除线，点一下就恢复。":
    "Rather than finding it in the waveform, **select the words** in the transcript (even a single word) and a bar appears below: **Cut this**, **Silence** one host, **▶ Play selection**, **Cancel**. Cut words are struck through, and a click restores them.",
  "忘了怎么操作？": "Forgot how?",
  "时间线标题旁的 **?** 里是所有鼠标和键盘操作：放大缩小（Ctrl + 滚轮）、左右移动、撤销（Ctrl + Z）……以后把鼠标移到 **?** 上就能看到。":
    "The **?** next to the timeline's title lists every mouse and keyboard action: zoom (Ctrl + wheel), moving left and right, undo (Ctrl + Z) … Point at the **?** any time to see it.",

  // 6 silence by hand
  "{b}说话时，{a}咳了一声": "{a} coughs while {b} talks",
  "删掉整段会把{b}的话也删了。先在{a}的轨道上拖选咳嗽那一小段（橙色虚线框）。":
    "Cutting it would cut {b}'s words too. First drag over the cough on {a}'s track (the dashed orange box).",
  "只静音一个人": "Silence one host only",
  "点 **只静音 {a}**：{b}的话留着，只把{a}那条轨道的这一下变安静。": "Click **Silence {a} only**: {b}'s words stay, and only {a}'s track goes quiet there.",
  "静音后继续": "Continues once it's silenced",
  "斜线 = 只删了一个人": "Stripes = one host only",
  "{a}的轨道上出现斜线，表示这里只静音了{a}。把鼠标移上去也能恢复。": "The stripes on {a}'s track show that only {a} was silenced here. Point at them to restore it.",
  "做错了也不怕": "Mistakes are fine",
  "每次改动后下面都会出现提示；按 **Ctrl + Z** 就撤销刚才那一下。所有改动都不碰原始录音。":
    "A notice appears after every change; **Ctrl + Z** undoes the last one. No change ever touches the original recording.",
  "剪辑做完了": "Editing is done",
  "点 **下一步：声音**，把两人的音量调一致。": "Click **Next: Volume** to make both hosts equally loud.",

  // 7 volume
  "一个大声，一个小声": "One loud, one quiet",
  "{a}离麦克风近，比{b}响很多。点 **统一两人音量**，LACUNA 把两人都调到同一个响度。":
    "{a} was close to the mic and is much louder than {b}. Click **Even out both hosts** and LACUNA brings both to the same loudness.",
  "点击后继续": "Continues once you click it",
  "看这把尺子": "Look at this meter",
  "白线是原始音量，彩色条是现在，绿线是目标。统一后两人的彩色条都到了绿线，右边的波形也一样高了。":
    "The white mark is the original loudness, the coloured bar is now, the green line is the target. After evening out, both bars reach the green line and the waveforms on the right are the same height.",
  "还想调，也可以": "Adjust it if you want",
  "拖滑块、点 **−1 / +1** 或点 **用建议值**。太响时会提示「最响的地方会被轻轻压住」。不调也没关系，这一步只是告诉你可以调。":
    "Drag the slider, click **−1 / +1**, or **Use suggested**. When it's too loud you'll see \"The loudest peaks will be gently limited\". You don't have to change anything; this is just so you know you can.",
  "LACUNA 会找出破音并自动修复。修不了的会列在这里，点时间就从前 2 秒开始听。示例里没有破音。":
    "LACUNA finds clipping and repairs it. Anything it can't repair is listed here; click a time to hear it from 2 s before. The sample has none.",
  "对比着听": "Compare by ear",
  "播放时点 **对比这里：原始 / 调整后**，听统一前后的差别。": "While playing, click **Compare here: original / adjusted** to hear the difference.",
  "声音好了": "Volume is done",
  "点 **下一步：配乐**。": "Click **Next: Music**.",

  // 8 music
  "左边是素材库": "The library is on the left",
  "示例准备了 3 首 CC0 授权的音乐。点 **▶** 能先试听。平时点上面的上传按钮，加你自己的。":
    "The sample comes with 3 CC0-licensed pieces. Click **▶** to hear one. Normally you'd add your own with the upload button above.",
  "放上片头": "Add an intro",
  "点第一首的 **放到 ▾**，选 **片头**。": "On the first piece, click **Place as ▾** and choose **Intro**.",
  "选好后继续": "Continues once it's placed",
  "片头放好了": "The intro is in",
  "右边多了一张「片头」卡片：歌名、在成品里的时间、试听、改类型、去掉。":
    "An Intro card appeared on the right: the song, where it sits in the final mix, play, change its use, remove.",
  "再放片尾": "Now an outro",
  "点第二首的 **放到 ▾**，选 **片尾**。": "On the second piece, click **Place as ▾** and choose **Outro**.",
  "这条线是音乐的音量": "This line is the music's volume",
  "点开片头卡片，就能看到：淡入 → 开头只放音乐 → 有人开口时自动压低 → 最后淡出。底下的色块是有人说话的地方。":
    "Open the intro card to see it: fade in → music alone at the start → lowered automatically when someone talks → fade out. The shaded band is where someone is talking.",
  "拖白点，调音乐": "Drag the white dots",
  "觉得说话时音乐还是有点吵？把「说话时压低」那个白点 **往下拖**。四个白点都能拖：左右改时间，上下改音量；也可以点一下白点再按方向键。":
    "Music still a bit loud under the talk? **Drag down** the \"Lower under talk\" dot. All four dots can be dragged: sideways changes the time, up and down the volume. You can also click a dot and use the arrow keys.",
  "拖一下白点后继续": "Continues once you've moved a dot",
  "不想拖，也能调数值": "Or set the numbers",
  "每个白点都有对应的滑块；数字可以直接输入后按回车，**− / +** 每次调一格。刚才拖的白点，就是这里的「说话时压低」。":
    "Each dot has a slider. Type a number and press Enter, or step it with **− / +**. The dot you dragged is \"Lower under talk\" here.",
  "「歌从 / 裁到」选用歌的哪一段；「位置」可以早 1 秒、晚 1 秒、±5 秒；还有各段淡入淡出的用时。":
    "\"Song from / Trim at\" pick which part of the song plays; \"Position\" moves it 1 s earlier or later, or ±5 s; and each fade's length is here.",
  "改完点 **试听这一处**，只听片头这一小段。": "After a change, click **Play this one** to hear just the intro.",
  "更多设置": "More settings",
  "试听后继续": "Continues once you've played it",
  "听整集成品": "The whole episode, finished",
  "这里放的是加了配乐的成品，导出的就是这一版。": "This plays the final mix with music: exactly what gets exported.",
  "说一句，让 LACUNA 调": "Say it, and LACUNA adjusts it",
  "不想自己调数值，也可以直接说。句子已经填好：「{text}」，点 **发送**。":
    "Rather than setting numbers, just say it. The sentence is filled in: \"{text}\". Click **Send**.",
  "采用，还是不要": "Adopt it, or not",
  "LACUNA 的改动先变成建议，可以点 **试听**。满意就点 **采用**，片头卡片上的曲线会跟着变；不满意就点「不要」。":
    "LACUNA's change is a suggestion first, and you can **Play** it. If you like it, click **Adopt** and the intro's curve changes; if not, \"Discard\".",
  "采用后继续": "Continues once it's adopted",
  "下一集不用再放一遍": "No need to do it again next time",
  "点 **设为默认片头片尾**，以后每一集都会自动放好同样的片头片尾和设置。旁边的「用在」可以选只这一集、本专辑或整个节目。":
    "Click **Make default intro & outro** and every new episode gets the same intro, outro and settings. \"Use for\" next to it chooses this episode only, the album or the whole show.",
  "BGM 署名": "Music credits",
  "用了谁的音乐，这里自动写好，发布时会放进节目简介。": "Whose music you used is written here for you, and goes into the episode description when you publish.",
  "配乐好了": "Music is done",
  "点 **下一步：导出**。": "Click **Next: Export**.",

  // 9 export
  "选格式": "Pick the formats",
  "**MP3** 体积小，适合分享；**WAV** 音质最好，上传平台用。可以都选。": "**MP3** is small, good for sharing; **WAV** has the best quality, for uploading to platforms. You can pick both.",
  "点 **开始导出**，几秒就好。": "Click **Start export**; it takes a few seconds.",
  "导出完继续": "Continues once it's exported",
  "下载成品": "Download it",
  "点 **下载**，这一集就做完了。": "Click **Download** and the episode is done.",
  "下载后继续": "Continues once it's downloaded",
  "这一集的结果": "This episode, in numbers",
  "右边是这一集的结果：原始多长、成品多长、剪掉多少、配乐几处、两人音量是否已统一。":
    "On the right: how long the recording was and the final episode is, how much was cut, how many music pieces, and whether both hosts are evened out.",
  "响度统一到 −16 LUFS，真峰值不超过 −1 dBTP，这是 Apple Podcasts、Spotify 等平台的标准，可以直接上传。":
    "Loudness at −16 LUFS with true peaks under −1 dBTP: the standard of Apple Podcasts, Spotify and others, so it's ready to upload.",
  "还有「发布」": "There's also Publish",
  "下一步「发布」里，LACUNA 会写标题、简介、show notes 和章节，还能做海报。示例就到这里，最后听一下前后对比。":
    "In the next step, Publish, LACUNA writes the title, description, show notes and chapters, and can make a poster. That's the end of the sample: one last before-and-after.",
};
