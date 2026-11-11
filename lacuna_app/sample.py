"""LACUNA 示例节目 (new-user batch, Leon 2026-10-22, Q4A / Q5A): a show of its own with one prepared episode in
the interface language, where a new person tries the whole flow (review → listen → music → export) in a few
minutes before importing their own recording.

The recording is shared: one read-only copy per language under ``<root>/sample/v<VERSION>/<lang>/raw``, built
once; every person's sample show gets only its own copy of the episode's edit list (state, transcript), which
points at those files. So it takes almost no disk, the original audio is never written, and "重置示例" just
copies the episode files again. The show is marked ``sample`` in the site database: it doesn't count against
the plan's show limit, and audio-hour metering (batch 5) must skip it too.

The voices are synthetic (Leon 2026-10-23, until he and Pei record the real sample): two stock voices of open
models read the script, one track per host (``sample_audio/<lang>/host0.flac``, ``host1.flac``), with the time
of every word from forced alignment (``tokens.json``); README.txt there names the models and licenses. Here we
only add the cough and make host 0 louder. Replacing it: new files there, then bump VERSION (old masters stay
until nobody's sample uses them).
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import soundfile as sf

from . import show
from .i18n import tr
from .store import atomic_write_json

VERSION = 3
EPISODE = "SAMPLE_01"
LANGS = ("zh", "en")
SR = 16000
NAME = {"zh": "LACUNA 示例节目", "en": "LACUNA Sample Show"}  # i18n-ignore
TITLE = {"zh": "示例 · 电影夜", "en": "Sample · Movie Night"}  # i18n-ignore
HOSTS = {"zh": ("小林", "阿乔"), "en": ("Sam", "Alex")}  # i18n-ignore
ABOUT = {"zh": "两位主持人聊一部刚看过的电影。（LACUNA 示例节目，声音为合成语音）",  # i18n-ignore
         "en": "Two hosts talk about a film they just watched. (LACUNA sample show, synthetic voices)"}

# (host 0/1, text, seconds of silence after). Placeholder script for the bubble tour (new-user batch, tour v3):
# 1:34 raw (zh; en 1:27). The first cut has five spots, three to review (a restart at 0:03, a tangent at about
# 0:20, a corrected score at about 0:26) and two routine ones (one 呃 / uh, one long pause), so → about 1:21.
# Then the tour asks LACUNA to drop Alex/阿乔's two lines about the actor's name (→ about 1:17), deletes
# 「等一下 我喝口水」 by hand (→ about 1:15) and mutes Sam/小林's cough under the other host (COUGH).
SCRIPT = {
    "zh": [
        (0, "大家好 欢迎收听电影夜 今天我们 今天我们聊一部 我们俩上周一起看的电影", 0.6),  # i18n-ignore
        (1, "对 就是那部讲一家人开面馆的片子", 0.5),  # i18n-ignore
        (0, "它的开头 呃 真的很抓人 一个长镜头从后厨一直跟到门口", 0.6),  # i18n-ignore
        (1, "那个镜头我数了 差不多三分钟没有剪", 0.5),  # i18n-ignore
        (0, "说到三分钟 我那天停车就找了三分钟 我表哥的车也停在那边 后来还被贴了罚单", 0.5),  # i18n-ignore
        (1, "好了好了 说回电影 先聊聊整体的感觉", 0.6),  # i18n-ignore
        (0, "我先说结论 这部片子我给打七分 不对 是八分", 0.6),  # i18n-ignore
        (1, "我也是八分 我最喜欢爸爸这个角色 他话很少 但每次做菜都像在说话", 0.6),  # i18n-ignore
        (1, "那个演员叫什么来着", 4.6),  # i18n-ignore
        (1, "想起来了 就是那位老演员", 0.7),  # i18n-ignore
        (0, "等一下 我喝口水", 1.6),  # i18n-ignore
        (0, "好 接着说 我觉得女儿那条线写得特别好 她一直想离开小镇 最后还是回来接手了面馆", 0.6),  # i18n-ignore
        (1, "对 这个结尾很克制 没有煽情 但我还是哭了", 0.5),  # i18n-ignore
        (0, "哈哈 我也哭了 尤其是最后那碗面 爸爸就多放了一个蛋", 0.6),  # i18n-ignore
        (1, "还有配乐也很好 几乎都是厨房里的声音 切菜 烧水 关火", 0.6),  # i18n-ignore
        (0, "对 我回家以后煮面的时候 一直在听自己家厨房的声音", 0.6),  # i18n-ignore
        (1, "所以我们的推荐是 去看 但是看之前一定要先吃饱", 0.5),  # i18n-ignore
        (0, "好 今天就聊到这里 谢谢大家 我们下期见", 0.4),  # i18n-ignore
        (1, "下期见", 1.6),  # i18n-ignore
    ],
    "en": [
        (0, "Hi everyone welcome to Movie Night today we're today we are talking about a film we both saw last week", 0.6),
        (1, "Right the one about the family noodle shop", 0.5),
        (0, "The opening uh was really gripping one long shot from the kitchen to the front door", 0.6),
        (1, "I counted almost three minutes without a cut", 0.5),
        (0, "Speaking of three minutes parking took me three minutes my cousin's car was there too and he got a ticket",
         0.5),
        (1, "Okay okay back to the movie and how it felt overall", 0.6),
        (0, "Bottom line I would give this film a seven no wait an eight", 0.6),
        (1, "Eight for me too I love the father he barely talks but his cooking says everything", 0.6),
        (1, "What was the actor called again", 4.6),
        (1, "Oh right the veteran one", 0.7),
        (0, "Hold on let me grab some water", 1.6),
        (0, "Okay so the daughter's story is great she wants to leave town and in the end she takes over the shop", 0.6),
        (1, "Yes and the ending is so restrained no big speeches but I still cried", 0.5),
        (0, "Me too especially the last bowl of noodles he says nothing and just adds an extra egg", 0.6),
        (1, "The music is great too mostly kitchen sounds chopping boiling water the stove clicking off", 0.6),
        (0, "I have been listening to my own kitchen ever since", 0.6),
        (1, "So our advice go see it but eat first", 0.5),
        (0, "That's it for today see you next time", 0.4),
        (1, "See you", 0.8),
    ],
}
# what the first cut does: (turn, words, op, category, reason, confidence) - the words are found inside that turn.
# Under 0.4 (review.REVIEW_CONFIDENCE) or a content cut goes to review; the rest is routine.
CUTS = {
    "zh": [
        (0, "今天我们", "cut", "repetition", "开头重说了一遍，保留第二遍", 0.35),  # i18n-ignore
        (2, "呃", "cut", "disfluency", "呃", 0.9),  # i18n-ignore
        (4, "说到三分钟 我那天停车就找了三分钟 我表哥的车也停在那边 后来还被贴了罚单", "cut", "content",  # i18n-ignore
         "停车和罚单是题外话，后面没有再提", 0.55),  # i18n-ignore
        (6, "七分 不对 是", "cut", "repetition", "说错又改口，留改口后的", 0.35),  # i18n-ignore
    ],
    "en": [
        (0, "today we're", "cut", "repetition", "Restarted the sentence, keep the second take", 0.35),
        (2, "uh", "cut", "disfluency", "uh", 0.9),
        (4, "Speaking of three minutes parking took me three minutes my cousin's car was there too and he got a ticket",
         "cut", "content", "The parking story is a tangent and never comes back", 0.55),
        (6, "a seven no wait", "cut", "repetition", "Said a score, then corrected it; keep the correction", 0.35),
    ],
}
LONG_PAUSE = 8      # the turn after which the long pause is tightened
COUGH = (12, 2.0, 0.45)  # host 0 coughs while host 1 says turn 12: seconds into the turn, how long
LOUD = (1.5, 0.5)   # host 0 sits close to the mic: about 9.5 dB louder (the tour's 统一两人音量 step)
MUSIC = Path(__file__).with_name("sample_music")   # CC0 tracks with licenses.json (trimmed copies)
AUDIO = Path(__file__).with_name("sample_audio")   # the two synthetic voices per language, word times


# the sentence the tour fills in (step 4): LACUNA's answer is scripted, so it never depends on the AI or quota
TOUR_CHAT = {"zh": "把阿乔问演员名字的那两句删掉", "en": "Cut Alex's two lines about the actor's name"}  # i18n-ignore
TOUR_LINES = (8, 9)     # the turns it removes
TOUR_MUSIC = {"zh": "说话时片头音乐再小一点", "en": "Make the intro music a bit quieter under the talk"}  # i18n-ignore


def _plain(text: str) -> str:
    return "".join(c for c in text.lower() if c.isalnum())


def tour_chat(ep, text: str, playhead: float) -> dict | None:
    """The tour's chat line in the sample episode → a proposal cutting those two lines (no AI call)."""
    from .editor import Proposal

    meta = getattr(ep, "meta", {}) or {}
    lang = meta.get("language")
    if meta.get("source") != "sample" or lang not in TOUR_CHAT or _plain(text) != _plain(TOUR_CHAT[lang]):
        return None
    first, last = (SCRIPT[lang][i][1] for i in TOUR_LINES)
    want = [c for c in (first + last) if c != " "] if lang == "zh" else (first + " " + last).split()
    with ep.lock:
        cuts = ep.cuts_for(ep.enabled)
        words = [w for w in ep.words(0.0, 1e9) if w[0] == HOSTS[lang][1]]
        seq = [w[3] for w in words]
        at = next((k for k in range(len(seq)) if seq[k:k + len(want)] == want), None)
        if at is None:
            return None
        a = to_tl_s(ep, words[at][1], cuts)
        b = to_tl_s(ep, words[at + len(want) - 1][2], cuts)
    if b - a < 0.5:     # already cut
        return None

    class Scripted:
        name = "sample"

        def propose(self, ctx):
            return Proposal(tr("好的：删掉 {a}–{b} {who}问演员名字的两句，共 {s} 秒，前后接得上。",
                               a=_mmss(a), b=_mmss(b), who=HOSTS[lang][1], s=f"{b - a:.1f}"),
                            action="cut", start=round(a - 0.05, 3), end=round(b + 0.25, 3),
                            title=tr("删掉{who}问演员名字的两句", who=HOSTS[lang][1]), reason=tr("按你的指令删掉"),
                            confidence=1.0)

    return ep.chat(text, playhead, Scripted())


def tour_music_chat(m, text: str) -> dict | None:
    """The tour's music line in the sample episode → a draft lowering the intro under the talk by 4 dB (no AI call)."""
    from .music import BG_DB
    from .music_assist import apply_actions

    meta = getattr(m.ep, "meta", {}) or {}
    lang = meta.get("language")
    if meta.get("source") != "sample" or lang not in TOUR_MUSIC or _plain(text) != _plain(TOUR_MUSIC[lang]):
        return None
    p = next((x for x in m.load()["placements"] if x["role"] == "intro"), None)
    if p is None:
        return {"message": tr("先从左边的素材库放一段片头，我再帮你调。"), "draft": None, "usage": None}
    bg = min(float(p.get("bg_db") if p.get("bg_db") is not None else BG_DB) + 4.0, 40.0)
    ps, changes = apply_actions(m, [{"type": "set", "placement_id": p["id"], "bg_db": bg}])
    msg = tr("好的：说话时把片头再压低 4 dB（共 {db} dB），音乐只在开头单独放时是全音量。先试听，满意就采用。", db=f"{bg:.0f}")
    m.set_draft(ps, changes, msg, "chat")
    return {"message": msg, "draft": m.draft_view(), "usage": None}


def tour_marks(ep) -> dict | None:
    """Where the tour's spots are on the current cut (seconds): the actor lines, 「等一下 我喝口水」, the silence
    after it, the cough."""
    meta = getattr(ep, "meta", {}) or {}
    lang = meta.get("language")
    if meta.get("source") != "sample" or lang not in SCRIPT:
        return None
    script = SCRIPT[lang]
    with ep.lock:
        cuts = ep.cuts_for(ep.enabled)
        words = ep.words(0.0, 1e9)

        def turn(i: int) -> tuple[float, float] | None:
            h, text, _ = script[i]
            mine = [w for w in words if w[0] == HOSTS[lang][h]]
            want = [c for c in text if c != " "] if lang == "zh" else text.split()
            seq = [w[3] for w in mine]
            at = next((k for k in range(len(seq)) if seq[k:k + len(want)] == want), None)
            return None if at is None else (mine[at][1], mine[at + len(want) - 1][2])

        def tl(span):
            return None if span is None else [round(to_tl_s(ep, span[0], cuts), 2), round(to_tl_s(ep, span[1], cuts), 2)]

        a, b = turn(TOUR_LINES[0]), turn(TOUR_LINES[1])
        c = turn(COUGH[0])
        return {"hosts": list(HOSTS[lang]),
                "actor": tl((a[0], b[1]) if a and b else None),
                "water": tl(turn(10)),
                # the silence after 「等一下 我喝口水」: no words, so the tour cuts it on the timeline
                "gap": tl((w[1], n[0]) if (w := turn(10)) and (n := turn(11)) else None),
                "cough": tl((c[0] + COUGH[1], c[0] + COUGH[1] + COUGH[2]) if c else None)}


def to_tl_s(ep, base_s: float, cuts) -> float:
    from .episode import to_tl

    return to_tl(int(base_s * ep.sr), cuts) / ep.sr


def turn_around(ep, span: tuple[int, int] | None) -> tuple[int, int] | None:
    """In the sample episode, an A/B plays only the sentence of the host whose words were cut, not 5 s either side
    with the other host cut off halfway (Leon 2026-10-23): base samples of that turn, or None (play as usual)."""
    meta = getattr(ep, "meta", {}) or {}
    if meta.get("source") != "sample" or not span:
        return None
    a, b = span[0] / ep.sr, span[1] / ep.sr
    words = ep.words(0.0, 1e9)
    inside = [k for k, w in enumerate(words) if w[1] < b and w[2] > a]
    if not inside:
        return None
    who = words[inside[0]][0]
    lo = hi = inside[0]
    while lo > 0 and words[lo - 1][0] == who:
        lo -= 1
    hi = inside[-1]
    while hi + 1 < len(words) and words[hi + 1][0] == who:
        hi += 1
    if any(words[k][0] != who for k in inside) or (words[lo][1] >= a - 0.05 and words[hi][2] <= b + 0.05):
        return None     # both hosts in the cut, or the whole sentence is cut: B would be silence
    pad = 0.25
    return int(max(words[lo][1] - pad, 0) * ep.sr), int((words[hi][2] + pad) * ep.sr)


def _mmss(s: float) -> str:
    return f"{int(s // 60)}:{int(s % 60):02d}"


def master(root: str | Path, lang: str) -> Path:
    """The shared sample for `lang` (built on first use): its workspace folder, holding the one episode."""
    lang = lang if lang in LANGS else "en"
    base = Path(root) / "sample" / f"v{VERSION}" / lang
    ws = base / "ws"
    if not (ws / "episodes" / EPISODE / "state.json").is_file():
        _build(base, lang)
    return ws


def give(root: str | Path, space: str | Path, lang: str) -> None:
    """Make `space` (a new show's folder) the sample show: profile, and a fresh copy of the episode."""
    lang = lang if lang in LANGS else "en"
    space = Path(space)
    a, b = HOSTS[lang]
    profile = show.normalise({"setup_done": True, "show_name": NAME[lang], "about": ABOUT[lang], "language": lang,
                              "hosts": [{"tag": "A", "name": a}, {"tag": "B", "name": b}]}, strict=False)
    atomic_write_json(space / show.FILE, profile)
    lib = master(root, lang) / "library"
    if lib.is_dir() and not (space / "library").exists():
        shutil.copytree(lib, space / "library")
    reset(root, space, lang)


def reset(root: str | Path, space: str | Path, lang: str) -> None:
    """重置示例: the episode back to the moment the first cut was done (the shared recording is untouched)."""  # i18n-ignore
    src = master(root, lang) / "episodes" / EPISODE
    dst = Path(space) / "episodes" / EPISODE
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def _turns(lang: str):
    """[(host, start, end, word)] per script turn, from the aligned recording; and its length in seconds."""
    lines = json.loads((AUDIO / lang / "tokens.json").read_text("utf-8"))
    out = []
    for (host, text, _), ln in zip(SCRIPT[lang], lines, strict=True):
        want = [c for c in text if c != " "] if lang == "zh" else text.split()
        got = [w for w, _, _ in ln["tokens"]]
        if ln["host"] != host or got != want:
            raise ValueError(f"sample_audio/{lang}/tokens.json does not match the script at {text!r}")
        out.append([(host, round(a, 3), round(b, 3), w) for w, a, b in ln["tokens"]])
    return out, sf.info(str(AUDIO / lang / "host0.flac")).duration


def _cough(n: int, rng) -> np.ndarray:
    """Two short noise bursts: a cough the listener should mute (the tour's 只静音 step)."""
    x = rng.standard_normal(n)
    t = np.arange(n) / n
    env = np.exp(-((t - 0.2) / 0.08) ** 2) + 0.7 * np.exp(-((t - 0.62) / 0.09) ** 2)
    return 0.35 * x * env


def _music(lib_dir: Path) -> None:
    """The sample show's library: three CC0 tracks (licenses.json), shared, credited, kinds set."""
    from .library import Library
    from .store import Workspace

    lib = Library(Workspace(lib_dir.parent))
    for e in json.loads((MUSIC / "licenses.json").read_text("utf-8")):
        a = lib.add_file(MUSIC / e["file"], e["kind"], note=f"{e['license']} · {e['track_page_url']}")
        with lib.lock:
            doc = lib.load()
            x = next(y for y in doc["assets"] if y["id"] == a["id"])
            x["credit"].update(title=e["title"], artist=e["artist"], status="confirmed", source="license",
                               sources=[e["track_page_url"], e["license_url"]])
            lib.save(doc)


def _build(base: Path, lang: str) -> None:
    from lacuna_core import MediaRef
    from .ai_cut import TrackTokens, build_episode
    from .episode import create_episode
    from .store import Workspace

    turns, _ = _turns(lang)
    names = HOSTS[lang]
    tags = ("A", "B")
    tmp = base.with_name(base.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    raw = tmp / "raw"
    raw.mkdir(parents=True)
    rng = np.random.default_rng(11)
    refs = {}
    for h, name in enumerate(names):
        x, sr = sf.read(str(AUDIO / lang / f"host{h}.flac"), dtype="float32")
        if sr != SR:
            raise ValueError(f"sample_audio/{lang}/host{h}.flac must be {SR} Hz")
        if x.ndim != 1:
            raise ValueError(f"sample_audio/{lang}/host{h}.flac must be mono")
        x = LOUD[h] * 0.55 * x / max(float(np.abs(x).max()), 1e-6)  # same peak for both, then host 0 louder
        if h == 0:
            ti, off, ln = COUGH
            i = int((turns[ti][0][1] + off) * SR)
            x[i:i + int(ln * SR)] += _cough(int(ln * SR), rng)[:len(x[i:i + int(ln * SR)])]
        path = raw / f"{name}.wav"
        sf.write(str(path), x.astype(np.float32), SR, subtype="PCM_16")
        refs[name] = path
    # the episode references the files where they will live, so write the audio there first
    final_raw = base / "raw"
    shutil.rmtree(base, ignore_errors=True)
    base.mkdir(parents=True)
    shutil.move(str(raw), str(final_raw))
    shutil.rmtree(tmp, ignore_errors=True)
    media = {name: MediaRef.probe(final_raw / f"{name}.wav") for name in names}

    ids: dict[int, list[str]] = {}
    tracks: dict[str, list[dict]] = {t: [] for t in tags}
    for ti, toks in enumerate(turns):
        ids[ti] = []
        for k, (h, a, b, w) in enumerate(toks):
            tid = f"{tags[h]}{len(tracks[tags[h]]):06d}"
            tracks[tags[h]].append({"id": tid, "t": w, "start": a, "end": b, "pause_after": 0.0, "flag": None})
            ids[ti].append(tid)
    ops = []
    for i, (ti, words, op, cat, reason, conf) in enumerate(CUTS[lang], 1):
        seq = [x[3] for x in turns[ti]]
        want = [c for c in words if c != " "] if lang == "zh" else words.split()
        at = next(k for k in range(len(seq)) if seq[k:k + len(want)] == want)
        host = tags[turns[ti][0][0]]
        ops.append({"id": f"op{i:04d}", "op": op, "track": host if cat != "content" else "both",
                    "from": ids[ti][at], "to": ids[ti][at + len(want) - 1], "category": cat, "reason": reason,
                    "confidence": conf})
    last = turns[LONG_PAUSE][-1][2]
    ops.append({"id": f"op{len(ops) + 1:04d}", "op": "tighten_pause", "track": "both", "at": round(last + 2.3, 3),
                "target_s": 0.6, "category": "pause",
                "reason": "空白 4.6 秒，收到 0.6 秒" if lang == "zh" else "A 4.6 s silence, tightened to 0.6 s",  # i18n-ignore
                "confidence": 0.85})
    doc = {"episode": EPISODE, "model": "sample", "ops": ops}
    tokens = {t: TrackTokens(v) for t, v in tracks.items()}
    project, edits, transcript, _ = build_episode(media, doc, tokens, 0.0, None, None, dict(zip(tags, names)))
    meta = {"title": TITLE[lang], "demo": False, "raw_offset_s": 0.0, "source": "sample", "language": lang}
    create_episode(Workspace(base / "ws"), EPISODE, meta, project, edits, transcript)
    _music(base / "ws" / "library")


# the 发布 chapter of the tour (Leon 2026-10-23, a locked demo: fixed content, no AI call). Placeholder words
# until Leon and Pei record the real sample; each timeline entry cites the first segment holding its key words.
PUBLISH = {
    "zh": {  # i18n-ignore
        "title": "电影夜：一碗面里的父亲", "alt_titles": ["长镜头、八分和一个蛋", "看之前先吃饱"],  # i18n-ignore
        "blurb": "两位主持人聊一部讲面馆一家人的电影：三分钟的长镜头、话很少的爸爸，和最后那碗面。",  # i18n-ignore
        "intro": "这一集我们聊一部上周一起看的电影。一家人开面馆，爸爸话很少，但每次做菜都像在说话；女儿一直想离开小镇，最后还是回来接手了面馆。我们各打了几分？听到最后你就知道。",  # i18n-ignore
        "sections": [("开场", [("电影夜", "开场：今天聊一部讲面馆一家人的电影"),  # i18n-ignore
                               ("长镜头", "开头三分钟不剪的长镜头")]),  # i18n-ignore
                     ("聊电影", [("八分", "两人都打八分，最喜欢话很少的爸爸"),  # i18n-ignore
                                ("女儿", "女儿那条线：想离开小镇，最后回来接手面馆"),  # i18n-ignore
                                ("结尾", "克制的结尾，最后那碗面多放了一个蛋"),  # i18n-ignore
                                ("配乐", "配乐几乎都是厨房里的声音")]),  # i18n-ignore
                     ("推荐", [("推荐", "我们的推荐：去看，但先吃饱")])],  # i18n-ignore
        "films": [{"name": "示例电影（面馆一家人）", "note": "本集主角"}],  # i18n-ignore
        "glossary": [{"term": "长镜头", "meaning": "一个镜头连续拍很久、中间不剪"}],  # i18n-ignore
    },
    "en": {
        "title": "Movie Night: A Father in a Bowl of Noodles", "alt_titles": ["One Long Shot and an Extra Egg"],
        "blurb": "Two hosts talk about a film on a family noodle shop: a three-minute long shot, a quiet father and that last bowl.",
        "intro": "This week we talk about a film we both saw: a family runs a noodle shop, the father barely talks but his cooking says everything, and the daughter wants to leave town until she doesn't. What did we give it? Listen to the end.",
        "sections": [("Opening", [("Movie Night", "Opening: a film about a family noodle shop"),
                                  ("long shot", "The three-minute long shot that opens it")]),
                     ("The film", [("Eight", "An eight from both of us, and the quiet father"),
                                   ("daughter", "The daughter's story: leaving town, then taking over the shop"),
                                   ("ending", "A restrained ending and one extra egg"),
                                   ("music", "Music made of kitchen sounds")]),
                     ("Verdict", [("advice", "Our advice: go see it, but eat first")])],
        "films": [{"name": "Sample film (the noodle shop family)", "note": "this episode's film"}],
        "glossary": [{"term": "long shot", "meaning": "one take that runs for a long time without a cut"}],
    },
}


def _lang(ep) -> str | None:
    meta = getattr(ep, "meta", {}) or {}
    return meta.get("language") if meta.get("source") == "sample" and meta.get("language") in PUBLISH else None


class SamplePublisher:
    """The sample episode's publish pack: written in advance, so the tour always shows the same thing."""

    name = "sample"
    available = True

    def __init__(self, lang: str):
        self.lang = lang

    def write(self, ep, segs, music, names, duration):
        from .publish import Draft

        p = PUBLISH[self.lang]

        def cite(key: str) -> str | None:
            k = _plain(key)
            return next((s.id for s in segs if k in _plain(s.text)), None)

        sections = [{"heading": h, "entries": [{"segment": sid, "text": text} for key, text in rows if (sid := cite(key))]}
                    for h, rows in p["sections"]]
        if not any(s["entries"] for s in sections) and segs:     # the words moved: one line at the start still shows the idea
            sections = [{"heading": p["sections"][0][0], "entries": [{"segment": segs[0].id, "text": p["sections"][0][1][0][1]}]}]
        data = {k: p[k] for k in ("title", "alt_titles", "blurb", "intro", "films", "glossary")}
        return Draft(data | {"sections": sections, "shows": [], "things": [], "names_to_check": []}, {}, self.name)


def sample_publisher(ep) -> SamplePublisher | None:
    lang = _lang(ep)
    return SamplePublisher(lang) if lang else None


# one cover per design direction; plain shapes and Latin text only (sanitize / the bundled Inter font)
_COVER = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 1200"><rect width="1200" height="1200" fill="{bg}"/>'
          '{art}<text x="90" y="1010" font-family="Inter" font-size="120" font-weight="700" fill="{fg}">MOVIE NIGHT</text>'
          '<text x="94" y="1090" font-family="Inter" font-size="44" fill="{fg}" opacity="0.7">LACUNA SAMPLE SHOW</text></svg>')
_ART = {
    "emblem": '<circle cx="600" cy="460" r="250" fill="none" stroke="#F2B66D" stroke-width="28"/><path d="M420 470 Q600 620 780 470" fill="none" stroke="#F2B66D" stroke-width="22"/><circle cx="600" cy="400" r="46" fill="#FFF4E0"/>',
    "pairing": '<rect x="140" y="170" width="420" height="600" fill="#2E4A62"/><rect x="640" y="170" width="420" height="600" fill="#C25B3C"/>',
    "geometry": '<rect x="120" y="140" width="960" height="40" fill="#E8D9B5"/><circle cx="820" cy="520" r="200" fill="#C25B3C"/><rect x="200" y="380" width="300" height="300" fill="#E8D9B5"/>',
    "free": '<path d="M150 700 L600 180 L1050 700 Z" fill="#3D6B5A"/><circle cx="600" cy="560" r="90" fill="#F6E7C1"/>',
}
_COLORS = {"emblem": ("#1C2433", "#FFF4E0"), "pairing": ("#F3EBDD", "#1C2433"), "geometry": ("#22313F", "#E8D9B5"),
           "free": ("#F6E7C1", "#1C2433")}


class SampleDesigner:
    """The sample episode's covers: drawn in advance (no AI call)."""

    name = "sample"
    available = True

    def design(self, context: str, direction: str):
        from .poster import Design

        k = direction if direction in _ART else "free"
        bg, fg = _COLORS[k]
        return Design(name=f"Sample {k.title()}", concept=tr("示例封面，节目录好后换成正式版本。"),
                      svg=_COVER.format(bg=bg, fg=fg, art=_ART[k]))

    def revise(self, context: str, svg: str, instruction: str):
        return self.design(context, "free")


def sample_designer(ep) -> SampleDesigner | None:
    return SampleDesigner() if _lang(ep) else None
