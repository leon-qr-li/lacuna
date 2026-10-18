"""Editor input for a new episode: tokens, acoustic features and the LLM-readable document.

Library port of spike S5 ``build_input.py`` (the input the v1-v3 first cuts were made from),
fed by ``lacuna_app.asr`` instead of S2 JSON files. Text and numbers only - this is everything
the AI editor ever sees of the audio. Ground-truth free.

    tokens, features, doc = build(asr={"L": ..., "P": ...}, audio={"L": x16k, "P": x16k}, episode="EP002")
"""
from __future__ import annotations

import difflib
import json
import re

import numpy as np

SR = 16000
HOP = 0.01                     # feature frame hop (s)
TRACKS = {"L": "Leon", "P": "Pei"}

# --------------------------------------------------------------------------- audio features


def frame_db(x, win=400, hop=160):
    n = 1 + (len(x) - win) // hop
    out = np.empty(n, dtype=np.float32)
    cols = np.arange(win)[None, :]
    for i in range(0, n, 50000):            # chunked to bound memory (the index too: n x win int64 is 2.3 GB for 2 h)
        j = min(i + 50000, n)
        fr = x[cols + hop * np.arange(i, j)[:, None]]
        out[i:j] = 10 * np.log10(np.mean(fr * fr, axis=1) + 1e-10)
    return out


def activity(db, floor, thr_db=12.0):
    """Boolean per-frame 'sound present' mask: floor-relative threshold, close gaps <60 ms,
    drop blips <30 ms."""
    a = db > floor + thr_db
    a = _fill_runs(a, False, 6)
    a = _fill_runs(a, True, 3)
    return a


def _fill_runs(mask, val, maxlen):
    m = mask.copy()
    n = len(m)
    i = 0
    while i < n:
        if m[i] == val:
            j = i
            while j < n and m[j] == val:
                j += 1
            if j - i < maxlen and i > 0 and j < n:
                m[i:j] = not val
            i = j
        else:
            i += 1
    return m


def runs(mask):
    """[(start_frame, end_frame_exclusive)] of True runs."""
    d = np.diff(np.concatenate([[0], mask.astype(np.int8), [0]]))
    return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))


def pitch_track(x, spans, act):
    """Simple normalized-autocorrelation F0 (60–400 Hz) on 40 ms frames / 10 ms hop, only inside
    the given (start_s, end_s) spans. Returns float array per 10 ms frame (nan = unvoiced)."""
    nfr = len(act)
    f0 = np.full(nfr, np.nan, dtype=np.float32)
    win, nfft = 640, 2048
    lmin, lmax = SR // 400, SR // 60
    w = np.hanning(win).astype(np.float32)
    frames = []
    for a, b in spans:
        frames.extend(range(int(a / HOP), min(nfr, int(b / HOP))))
    frames = np.array(sorted(set(frames)), dtype=np.int64)
    frames = frames[act[frames]]
    for i in range(0, len(frames), 20000):
        fi = frames[i:i + 20000]
        st = fi * 160 + 200 - win // 2
        st = np.clip(st, 0, len(x) - win)
        fr = x[st[:, None] + np.arange(win)[None, :]] * w
        fr = fr - fr.mean(axis=1, keepdims=True)
        sp = np.fft.rfft(fr, nfft)
        ac = np.fft.irfft(sp * np.conj(sp), nfft)[:, :lmax + 2]
        ac = ac / (ac[:, :1] + 1e-9)
        seg = ac[:, lmin:lmax + 1]
        k = np.argmax(seg, axis=1)
        pk = seg[np.arange(len(k)), k]
        lag = (k + lmin).astype(np.float64)
        # parabolic interpolation
        km = np.clip(k + lmin, 1, lmax)
        y0, y1, y2 = ac[np.arange(len(k)), km - 1], ac[np.arange(len(k)), km], ac[np.arange(len(k)), km + 1]
        den = (y0 - 2 * y1 + y2)
        lag = lag + np.where(np.abs(den) > 1e-9, 0.5 * (y0 - y2) / den, 0)
        voiced = (pk > 0.5) & (lag > SR / 450) & (lag < SR / 55)
        f0[fi[voiced]] = (SR / lag[voiced]).astype(np.float32)
    return f0


# --------------------------------------------------------------------------- tokens


def merge_bpe(tokens):
    """Merge sherpa BPE pieces ('v@@','ac@@','ation') into words; strip SenseVoice spaces."""
    out, buf = [], None
    for t in tokens:
        s = t["t"].strip()
        if not s:
            continue
        if buf is not None:
            buf["t"] += s.replace("@@", "")
            buf["end"] = t["end"]
            if not s.endswith("@@"):
                out.append(buf)
                buf = None
            continue
        if s.endswith("@@"):
            buf = {"t": s[:-2], "start": t["start"], "end": t["end"]}
        else:
            out.append({"t": s, "start": t["start"], "end": t["end"]})
    if buf is not None:
        out.append(buf)
    return out


def is_ascii(s):
    return bool(re.match(r"^[A-Za-z0-9'.\-]+$", s))


def sv_units(tokens):
    """SenseVoice tokens -> units comparable to Paraformer tokens (CJK char or ASCII word)."""
    out = []
    for t in tokens:
        s = t["t"].strip()
        if not s:
            continue
        if is_ascii(s):
            out.append(s.lower())
        else:
            out.extend(list(s))
    return out


def build_tokens(asr, db, act, tag):
    """Return tokens list and per-segment index ranges (both engines decoded the same VAD segments)."""
    nfr = len(act)
    toks, segs = [], []
    for si, seg in enumerate(asr["segments"]):
        ps = {"start": seg["start"], "end": seg["end"], **seg["par"]}
        ss = {"start": seg["start"], "end": seg["end"], **seg["sv"]}
        pt = merge_bpe(ps["tokens"])
        i0 = len(toks)
        for t in pt:
            toks.append({"id": None, "t": t["t"], "start": t["start"], "asr_start": t["start"],
                         "seg": si, "flag": None})
        # disagreement flags (Paraformer vs SenseVoice, unit-level diff inside the same VAD segment)
        pu = [t["t"].lower() if is_ascii(t["t"]) else t["t"] for t in pt]
        su = sv_units(ss["tokens"])
        sm = difflib.SequenceMatcher(a=pu, b=su, autojunk=False)
        for op, a0, a1, b0, b1 in sm.get_opcodes():
            if op == "equal":
                continue
            alt = "".join((" " + u + " ") if is_ascii(u) else u for u in su[b0:b1]).strip()
            alt = re.sub(r"\s+", " ", alt)
            if a1 > a0:
                for k in range(a0, a1):
                    toks[i0 + k]["flag"] = {"kind": op, "span": [i0 + a0, i0 + a1 - 1], "sv": alt}
            else:  # SenseVoice has extra units that Paraformer lacks -> attach to the previous token
                k = max(a0 - 1, 0)
                if i0 + k < len(toks) and toks[i0 + k]["flag"] is None and len(pt):
                    toks[i0 + k]["flag"] = {"kind": "sv_insert_after", "span": [i0 + k, i0 + k], "sv": alt}
        segs.append({"seg": si, "start": ps["start"], "end": ps["end"], "tok": [i0, len(toks)],
                     "sv_event": ss.get("event"), "sv_emotion": ss.get("emotion"),
                     "par_text": ps["text"], "sv_text": ss["text"]})
    # ids
    for i, t in enumerate(toks):
        t["id"] = f"{tag}{i:06d}"
    # energy refinement of start, end = min(next start, energy offset)
    for i, t in enumerate(toks):
        s = t["start"]
        f = int(round(s / HOP))
        lo = max(0, int(round((s - 0.15) / HOP)))
        if i > 0:
            lo = max(lo, int(round(toks[i - 1]["asr_start"] / HOP)) + 1)
        w = act[lo:f + 1]
        if len(w) and not w.all():
            last_off = lo + np.where(~w)[0][-1]
            nf = last_off + 1
            if nf <= f and act[min(nf, nfr - 1)]:
                s = nf * HOP
        t["start"] = round(s, 2)
    for i, t in enumerate(toks):
        seg = segs[t["seg"]]
        nxt = toks[i + 1]["start"] if i + 1 < len(toks) else seg["end"]
        cap = min(nxt, t["start"] + 1.2)
        if i + 1 < len(toks) and toks[i + 1]["seg"] != t["seg"]:
            cap = min(cap, seg["end"])
        f = int(round(t["start"] / HOP))
        fc = int(round(cap / HOP))
        # walk forward while sound present (gaps <=80 ms tolerated)
        e, gap = f, 0
        j = f
        while j < min(fc, nfr):
            if act[j]:
                e, gap = j + 1, 0
            else:
                gap += 1
                if gap > 8:
                    break
            j += 1
        end = max(e * HOP, t["start"] + 0.06)
        end = min(end, cap) if cap > t["start"] + 0.06 else t["start"] + 0.06
        t["end"] = round(end, 2)
    for i, t in enumerate(toks):
        nxt = toks[i + 1]["start"] if i + 1 < len(toks) else None
        t["pause_after"] = round(max(0.0, nxt - t["end"]), 2) if nxt is not None else None
    return toks, segs


# --------------------------------------------------------------------------- utterance features


def semitones(f, ref):
    return 12 * np.log2(f / ref)


def utt_features(toks, segs, db, f0, speech_ref_db, f0_ref):
    utts = []
    for s in segs:
        a, b = s["tok"]
        u = {"seg": s["seg"], "tok": [a, b], "vad": [s["start"], s["end"]],
             "sv_event": s["sv_event"], "sv_emotion": s["sv_emotion"]}
        if b == a:
            u.update({"start": s["start"], "end": s["end"], "empty": True})
            fr = slice(int(s["start"] / HOP), int(s["end"] / HOP))
            e = db[fr]
            # past the end of a track that stopped early there is no audio: as quiet as the track gets
            u["energy_rel_db"] = round(float((np.percentile(e, 90) if len(e) else db.min()) - speech_ref_db), 1)
            utts.append(u)
            continue
        T = toks[a:b]
        st, en = T[0]["start"], T[-1]["end"]
        nunits = sum(1 for t in T)
        inner_pause = sum(t["pause_after"] for t in T[:-1] if t["pause_after"] and t["pause_after"] >= 0.3)
        spoken = max(en - st - inner_pause, 0.2)
        fr = np.concatenate([np.arange(int(t["start"] / HOP), int(t["end"] / HOP)) for t in T])
        fr = fr[fr < len(db)]
        e = db[fr]
        u.update({"start": st, "end": en, "empty": False, "n": nunits,
                  "rate": round(nunits / spoken, 1),
                  "energy_rel_db": round(float((10 * np.log10(np.mean(10 ** (e / 10))) if len(e) else db.min())
                                               - speech_ref_db), 1)})
        p = f0[fr]
        v = ~np.isnan(p)
        if v.sum() >= 5:
            stv = semitones(p[v], f0_ref)
            u["f0_med_st"] = round(float(np.median(stv)), 1)
            u["f0_range_st"] = round(float(np.percentile(stv, 90) - np.percentile(stv, 10)), 1)
            # final contour: last 0.6 s of voiced frames inside the last tokens
            tail = fr[(fr >= int((en - 0.6) / HOP))]
            tp = f0[tail]
            tv = ~np.isnan(tp)
            if tv.sum() >= 5:
                y = semitones(tp[tv], f0_ref)
                x = tail[tv] * HOP
                slope = np.polyfit(x, y, 1)[0]
                delta = slope * (x[-1] - x[0])
                u["end_contour"] = "rise" if delta > 1.5 else ("fall" if delta < -1.5 else "flat")
                u["end_delta_st"] = round(float(delta), 1)
        utts.append(u)
    return utts


# --------------------------------------------------------------------------- main


def build(asr: dict, audio: dict, episode: str, log=print) -> tuple[dict, dict, str]:
    """(tokens doc, features doc, editor document) from per-track ASR + 16 kHz mono audio."""
    data = {}
    for tag, name in TRACKS.items():
        x = audio[tag]
        db = frame_db(x)
        floor = float(np.percentile(db, 10))
        act = activity(db, floor)
        toks, segs = build_tokens(asr[tag], db, act, tag)
        tok_fr = np.zeros(len(db), bool)
        for t in toks:
            tok_fr[int(t["start"] / HOP):int(t["end"] / HOP)] = True
        speech_ref_db = float(np.median(db[tok_fr & act])) if (tok_fr & act).any() else float(np.median(db))
        f0 = pitch_track(x, [(t["start"], t["end"]) for t in toks], act)
        f0v = f0[~np.isnan(f0)]
        f0_ref = float(np.median(f0v)) if len(f0v) else 150.0
        utts = utt_features(toks, segs, db, f0, speech_ref_db, f0_ref)
        data[tag] = dict(x_dur=len(x) / SR, db=db, act=act, floor=floor, toks=toks, segs=segs, utts=utts,
                         tok_fr=tok_fr, speech_ref_db=speech_ref_db, f0_ref=f0_ref)
        log(f"{name}: {len(toks)} tokens, {len(utts)} utts, floor {floor:.1f} dB, speech {speech_ref_db:.1f} dB, "
              f"f0 median {f0_ref:.0f} Hz, flagged {sum(1 for t in toks if t['flag'])}")

    # utterance pause before/after (same track, token-based)
    for tag, d in data.items():
        spoken = [u for u in d["utts"] if not u["empty"]]
        for i, u in enumerate(spoken):
            u["pause_before"] = round(u["start"] - spoken[i - 1]["end"], 2) if i else None
            u["pause_after"] = round(spoken[i + 1]["start"] - u["end"], 2) if i + 1 < len(spoken) else None

    # overlaps: both tracks inside token spans simultaneously (token spans, gaps <=0.3 s bridged)
    nfr = min(len(data["L"]["db"]), len(data["P"]["db"]))
    def talk_mask(d):
        m = np.zeros(nfr, bool)
        for t in d["toks"]:
            m[int(t["start"] / HOP):int(t["end"] / HOP)] = True
        return _fill_runs(m, False, 30)
    mL, mP = talk_mask(data["L"]), talk_mask(data["P"])
    both = mL & mP
    overlaps = []
    for s, e in runs(both):
        if e - s < 20:            # ignore <0.2 s
            continue
        st, en = s * HOP, e * HOP
        # who started first: start of the talk run each track is in
        def run_start(m):
            j = s
            while j > 0 and m[j - 1]:
                j -= 1
            return j * HOP
        sL, sP = run_start(mL), run_start(mP)
        first = "L" if sL < sP - 0.05 else ("P" if sP < sL - 0.05 else "same")
        def toks_in(d):
            return [t for t in d["toks"] if t["end"] > st and t["start"] < en]
        tl, tp = toks_in(data["L"]), toks_in(data["P"])
        overlaps.append({"start": round(st, 2), "end": round(en, 2), "dur": round(en - st, 2), "first": first,
                         "L": [tl[0]["id"], tl[-1]["id"], "".join(t["t"] for t in tl)] if tl else None,
                         "P": [tp[0]["id"], tp[-1]["id"], "".join(t["t"] for t in tp)] if tp else None})

    # long silences: neither track has sound (energy activity) for >= 1.5 s
    anyact = data["L"]["act"][:nfr] | data["P"]["act"][:nfr]
    silences = [{"start": round(s * HOP, 2), "end": round(e * HOP, 2), "dur": round((e - s) * HOP, 2)}
                for s, e in runs(~anyact) if e - s >= 150]
    # floor gaps: neither track has a token (speech) for >= 1.0 s (more useful than raw energy)
    talk_any = mL | mP
    gaps = [{"start": round(s * HOP, 2), "end": round(e * HOP, 2), "dur": round((e - s) * HOP, 2)}
            for s, e in runs(~talk_any) if e - s >= 100]

    # non-speech sound candidates: active energy >= 0.25 s with no token within 0.1 s, loud enough
    sounds = []
    for tag, d in data.items():
        cover = np.zeros(len(d["act"]), bool)
        for t in d["toks"]:
            cover[max(0, int(t["start"] / HOP) - 10):int(t["end"] / HOP) + 10] = True
        for s, e in runs(d["act"] & ~cover):
            if e - s < 25:
                continue
            pk = float(np.percentile(d["db"][s:e], 90) - d["speech_ref_db"])
            if pk < -8:
                continue
            sounds.append({"track": tag, "start": round(s * HOP, 2), "end": round(e * HOP, 2),
                           "dur": round((e - s) * HOP, 2), "peak_rel_db": round(pk, 1), "src": "energy"})
        for u in d["utts"]:
            seg = d["segs"][u["seg"]]
            txt = seg["par_text"]
            if u["sv_event"] in ("Laughter", "Breath", "Cough") or re.search(r"(哈|呵){2,}", txt):
                sounds.append({"track": tag, "start": u["start"], "end": u["end"],
                               "dur": round(u["end"] - u["start"], 2),
                               "peak_rel_db": u.get("energy_rel_db"),
                               "src": "sv:" + (u["sv_event"] or "") if u["sv_event"] != "Speech" else "text:哈哈"})
    sounds.sort(key=lambda s: s["start"])

    # stats
    stats = {}
    for tag, d in data.items():
        sp = [u for u in d["utts"] if not u["empty"]]
        pa = np.array([t["pause_after"] for t in d["toks"] if t["pause_after"] is not None])
        stats[tag] = {"duration_s": round(d["x_dur"], 2), "tokens": len(d["toks"]), "utterances": len(sp),
                      "empty_vad_segments": len(d["utts"]) - len(sp),
                      "speech_s": round(float(d["tok_fr"].sum() * HOP), 1),
                      "median_rate": round(float(np.median([u["rate"] for u in sp])), 1),
                      "f0_median_hz": round(d["f0_ref"]),
                      "noise_floor_db": round(d["floor"], 1), "speech_level_db": round(d["speech_ref_db"], 1),
                      "asr_disagree_tokens": sum(1 for t in d["toks"] if t["flag"]),
                      "token_pauses_ge_0.3": int((pa >= 0.3).sum()), "token_pauses_ge_1.0": int((pa >= 1.0).sum())}
    stats["overlap"] = {"count": len(overlaps), "total_s": round(sum(o["dur"] for o in overlaps), 1),
                        "L_first": sum(o["first"] == "L" for o in overlaps),
                        "P_first": sum(o["first"] == "P" for o in overlaps)}
    stats["floor_gaps_ge_1s"] = {"count": len(gaps), "total_s": round(sum(g["dur"] for g in gaps), 1)}
    stats["sound_candidates"] = len(sounds)

    tok_out = {"episode": episode, "time_base": "raw seconds of each track (tracks start in sync)",
               "tracks": {tag: [{k: t[k] for k in ("id", "t", "start", "end", "pause_after", "flag")}
                                for t in d["toks"]] for tag, d in data.items()}}
    feat_out = {"episode": episode, "stats": stats, "overlaps": overlaps, "long_silences": silences,
                "floor_gaps": gaps, "sounds": sounds,
                "utterances": {tag: [{k: v for k, v in u.items()} for u in d["utts"]] for tag, d in data.items()}}
    return tok_out, feat_out, write_doc(episode, data, stats, overlaps, gaps, silences, sounds)


# --------------------------------------------------------------------------- document

FORMAT_HELP = """\
## 格式说明 (format)

时间一律为**原始音轨秒数** (raw seconds; 两轨从 0 起同步)。L = Leon 轨, P = Pei 轨。按开始时间交错排列，读起来就是对话本身。

每行一句 (= 一个 VAD 语段):
`L 123.45-129.80 r5.1 e+2 ↗ pb0.62 pa1.20 ov | @812 我觉得这个电影吧 (0.45) @820 就是{那那|那}边 …`

- 头部: 轨 · 起止秒 · `r` 语速 (字/秒, 去掉句内≥0.3 s 停顿) · `e` 相对该轨正常说话音量 (dB, 已按轨归一) · 句尾音高 `↗`升 `↘`降 `→`平 (缺省=测不到) · `pb`/`pa` 同轨上一句/下一句的间隔秒 · `ov` = 本句与另一轨重叠 (见重叠表)
- `@812` = 锚点: 后面第一个字的 token id 是 `L000812` (P 行则 `P000812`)。后续每个字 / 英文词各占一个连续 id: `@812 我觉得` → 我=L000812, 觉=L000813, 得=L000814。锚点出现在行首、每个停顿后、以及每 10 个 token。
- `(0.45)` = 前一个 token 后面的停顿 ≥0.30 s (同轨)。
- `{那那|那}` = Paraformer 与 SenseVoice 不一致: 左边是带 id 的 Paraformer 文本, 右边是 SenseVoice 的读法 (无 id)。`{|嗯}` 表示只有 SenseVoice 听到了 (附在前一个 token 后); `{对|}` 表示只有 Paraformer 听到了。不一致处多为语气词/重复/英文/专名, 文本不可全信, 删改要更保守。
- `~snd 0.45s e-3 [sv:Laughter]` = 无 ASR 文字的声音候选 (笑声/呼吸/咳嗽/碰麦/口水声都有可能; 仅凭能量, 不确定)。
- `L ... (no text) e-12` = VAD 认为有声但两个 ASR 都没出字。
- `--- 12:00 ---` = 每分钟一条时间刻度 (raw)。
- `== 地板间隙 2.31s (raw 300.12-302.43) ==` = 两轨都没有说话 ≥1.0 s 的位置 (可能是可收紧的停顿)。
"""


def fmt_utt_line(tag, u, d, ov_ranges):
    T = d["toks"]
    a, b = u["tok"]
    head = f"{tag} {u['start']:.2f}-{u['end']:.2f}"
    if u["empty"]:
        ev = f" [sv:{u['sv_event']}]" if u["sv_event"] and u["sv_event"] != "Speech" else ""
        return f"{head} (no text) e{u['energy_rel_db']:+.0f}{ev}"
    head += f" r{u['rate']}"
    head += f" e{u['energy_rel_db']:+.0f}"
    c = u.get("end_contour")
    if c:
        head += {"rise": " ↗", "fall": " ↘", "flat": " →"}[c]
    if u.get("pause_before") is not None:
        head += f" pb{u['pause_before']:.2f}"
    if u.get("pause_after") is not None:
        head += f" pa{u['pause_after']:.2f}"
    if any(s < u["end"] and e > u["start"] for s, e in ov_ranges):
        head += " ov"
    if u["sv_event"] and u["sv_event"] != "Speech":
        head += f" [sv:{u['sv_event']}]"
    if u.get("sv_emotion") in ("HAPPY", "ANGRY", "SAD", "SURPRISED", "DISGUSTED"):
        head += f" emo:{u['sv_emotion'].lower()}"
    parts = []
    since = 99
    prev_ascii = False
    i = a
    while i < b:
        t = T[i]
        anchor = since >= 10 or i == a or (i > a and T[i - 1]["pause_after"] and T[i - 1]["pause_after"] >= 0.3)
        if anchor:
            parts.append(f" @{i} ")
            since = 0
            prev_ascii = False
        fl = t["flag"]
        if fl and fl["kind"] != "sv_insert_after" and fl["span"][0] == i:
            j1 = min(fl["span"][1], b - 1)
            txt = _join(T[i:j1 + 1])
            parts.append(f"{{{txt}|{fl['sv']}}}")
            since += j1 - i + 1
            last = T[j1]
            i = j1 + 1
        else:
            s = t["t"]
            if is_ascii(s):
                s = (" " if not anchor else "") + s + " "
            parts.append(s)
            since += 1
            last = t
            i += 1
            if fl and fl["kind"] == "sv_insert_after":
                parts.append(f"{{|{fl['sv']}}}")
        if i < b and last["pause_after"] and last["pause_after"] >= 0.3:
            parts.append(f" ({last['pause_after']:.2f})")
    body = re.sub(r" +", " ", "".join(parts)).strip()
    return f"{head} |{' ' if not body.startswith('@') else ' '}{body}"


def _join(ts):
    out = ""
    for t in ts:
        out += (" " + t["t"] + " ") if is_ascii(t["t"]) else t["t"]
    return re.sub(r" +", " ", out).strip()


def write_doc(episode, data, stats, overlaps, gaps, silences, sounds):
    L, P = stats["L"], stats["P"]
    lines = [f"# {episode} 剪辑输入 (editor input) — 《洛城二三事》", "",
             "只含文字与数值特征 (无音频)。原始双轨来自 Riverside 分轨录音: L 轨只有 Leon 的麦, P 轨只有 Pei 的麦, 两轨时间轴一致。", "",
             FORMAT_HELP, "## 概览 (overview)", "",
             f"- 原始时长: L {L['duration_s']:.1f}s, P {P['duration_s']:.1f}s ({L['duration_s']/60:.1f} min)",
             "| 轨 | token 数 | 句数 | 说话秒数 | 语速中位 (字/s) | F0 中位 | ASR 不一致 token | 同轨 token 间停顿≥0.3s | ≥1.0s |",
             "|---|---|---|---|---|---|---|---|---|"]
    for tag in ("L", "P"):
        s = stats[tag]
        lines.append(f"| {tag} | {s['tokens']} | {s['utterances']} | {s['speech_s']} | {s['median_rate']} | "
                     f"{s['f0_median_hz']} Hz | {s['asr_disagree_tokens']} | {s['token_pauses_ge_0.3']} | {s['token_pauses_ge_1.0']} |")
    lines += ["", f"- 原始电平: L 说话 {L['speech_level_db']} dBFS (底噪 {L['noise_floor_db']}), "
              f"P 说话 {P['speech_level_db']} dBFS (底噪 {P['noise_floor_db']}); `e` 已按轨归一。",
              f"- 两轨同时说话 (≥0.2 s): {stats['overlap']['count']} 处, 共 {stats['overlap']['total_s']} s; "
              f"L 先开口 {stats['overlap']['L_first']} 次, P 先开口 {stats['overlap']['P_first']} 次。",
              f"- 地板间隙 (两轨都没说话 ≥1.0 s): {stats['floor_gaps_ge_1s']['count']} 处, 共 {stats['floor_gaps_ge_1s']['total_s']} s。",
              f"- 两轨都完全无声 ≥1.5 s: {len(silences)} 处。", f"- 无文字声音候选: {len(sounds)} 个。", "",
              "### 重叠表 (overlaps)", "",
              "`起-止 时长 先开口者(L/P/same=同时) | L: 首id-末id 重叠部分文本 | P: 首id-末id 重叠部分文本`", ""]
    for o in overlaps:
        lt = f"{o['L'][0]}-{o['L'][1]} {o['L'][2]}" if o["L"] else "-"
        pt = f"{o['P'][0]}-{o['P'][1]} {o['P'][2]}" if o["P"] else "-"
        lines.append(f"- {o['start']:.2f}-{o['end']:.2f} {o['dur']:.2f}s {o['first']} | L: {lt} | P: {pt}")
    lines += ["", "## 全文 (transcript, chronological)", ""]

    events = []
    ovr = [(o["start"], o["end"]) for o in overlaps]
    for tag, d in data.items():
        for u in d["utts"]:
            events.append((u["start"], 0, fmt_utt_line(tag, u, d, ovr)))
    for s in sounds:
        if s["src"] == "energy":
            events.append((s["start"], 1, f"{s['track']} {s['start']:.2f}-{s['end']:.2f} ~snd {s['dur']:.2f}s e{s['peak_rel_db']:+.0f}"))
        else:
            pass  # sv / 哈哈 flags are already on the utterance line
    for g in gaps:
        events.append((g["start"], 2, f"== 地板间隙 {g['dur']:.2f}s (raw {g['start']:.2f}-{g['end']:.2f}) =="))
    dur = max(data["L"]["x_dur"], data["P"]["x_dur"])
    for m in range(1, int(dur // 60) + 1):
        events.append((m * 60.0, -1, f"--- {m:02d}:00 ---"))
    events.sort(key=lambda e: (e[0], e[1]))
    lines += [e[2] for e in events]
    return "\n".join(lines) + "\n"
