"""Voice and music levels (backlog items 7 and 20): even host loudness from import on, a per-track
gain Leon can change (「声音」 page or the editing chat), and music levelled on what actually plays.

* Each host track of the uncut recording is measured once (BS.1770 integrated loudness on the
  dual-mono scale `music.voice_lufs` uses, sample peak, a robust "loud peak") as recorded and
  cached in ``<episode>/levels.json``. Reading is a straight pass over the source clips, so an hour
  of audio takes seconds.
* The level of a track is a `track_gain` edit (category ``loudness``, source ``level``): review
  playback and export already honour it, undo/redo comes for free, and at most one such edit per
  track is in effect. A new import gets them as part of its first state (no undo step); an older
  episode is levelled only when Leon asks (button or chat).
* Target: every host at TARGET_LUFS. Gains are capped so a track's loud peaks stay under the
  renderer's soft-clip knee (-1 dBFS); when one track cannot reach the target, both aim lower (up
  to MAX_SHORTFALL) so the two stay even. Export mastering (lacuna_core/master.py) measures the
  whole mix again and normalises it, so these gains change the balance, never stack loudness.
* Clipping in a source is repaired automatically where that is safe (`declip.py`, decision
  2026-10-18-auto-declip); the page says how many spots were repaired and lists the ones left as
  recorded.
* Music: full level = voice loudness + `music.LEVEL_LU`, measured on the part of the song that
  plays (src_in..src_out) rather than the whole file, so a quiet opening or a loud finale that is
  trimmed away does not throw the level off. Leon's「音量（dB）」 stays an offset on top.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import threading
from collections import OrderedDict

import numpy as np

from lacuna_core import SourcePool
from lacuna_core.master import LoudnessMeter

from . import declip
from .episode import APPLIED, DISCARDED, PROPOSED, ConflictError, Episode, to_tl
from .i18n import tr
from .store import atomic_write_json, read_json, now_iso as _now

FILE = "levels.json"
SCHEMA = 1
TARGET_LUFS = -20.0         # each host's speech, dual-mono LUFS (a mono track as heard on two speakers)
PEAK_CEIL_DB = -1.0         # renderer soft-clip knee: loud peaks should stay below it
MAX_SHORTFALL = 6.0         # how far under the target both hosts may go to keep one track's peaks clean
GAIN_MIN, GAIN_MAX = -20.0, 24.0
STEP_DB = 2.0               # "太低" / "大一点" without a number
SMALL_STEP_DB = 1.0         # "稍微 / 一点点"
CLIP_TIMES = 30             # unrepaired clipping spots listed per track
_BLOCK_S = 10.0

_lock = threading.Lock()
_music_cache: OrderedDict[tuple, float | None] = OrderedDict()


def _db(x: float) -> float | None:
    return round(20 * math.log10(x), 2) if x > 0 else None


# ===================================================================== measuring

def _track_key(ep: Episode, name: str) -> str:
    tr_ = ep.base.track(name)
    clips = [(c.media_id, c.src_in, c.src_out, c.start, c.gain_db) for c in tr_.clips]
    return hashlib.sha1(json.dumps([ep.sr, tr_.gain_db, clips]).encode()).hexdigest()[:16]


def measure_track(ep: Episode, name: str) -> dict:
    """Loudness and peaks of one host track of the uncut recording as recorded (base samples)."""
    sr = ep.sr
    tr_ = ep.base.track(name)
    meter = LoudnessMeter(sr, 1, dual_mono=True, true_peak=False)
    peak = 0.0
    maxima: list[np.ndarray] = []            # max |x| per 10 ms, for the robust loud peak
    hop = max(1, int(0.01 * sr))
    block = int(_BLOCK_S * sr)
    with SourcePool(ep.media, repaired=False) as pool:
        for c in sorted(tr_.clips, key=lambda c: c.start):
            g = 10 ** ((c.gain_db + tr_.gain_db) / 20)
            for s in range(c.src_in, c.src_out, block):
                e = min(s + block, c.src_out)
                x = pool.read(c.media_id, s, e)
                x = x * g if g != 1.0 else x
                meter.add(x)
                a = np.abs(x)
                peak = max(peak, float(a.max(initial=0.0)))
                k = len(a) // hop
                if k:
                    maxima.append(a[:k * hop].reshape(k, hop).max(axis=1))
    lufs = meter.integrated()
    m = np.concatenate(maxima) if maxima else np.zeros(0)
    loud = float(np.percentile(m, 99.9)) if len(m) else 0.0
    return {"lufs": round(lufs, 2) if math.isfinite(lufs) else None, "peak_db": _db(peak),
            "loud_peak_db": _db(loud), "seconds": round(sum(c.src_out - c.src_in for c in tr_.clips) / sr, 1)}


def voice_tracks(ep: Episode) -> list[str]:
    """The host tracks (music is a separate layer and never on the voice timeline)."""
    return [t.name for t in ep.base.tracks if t.clips]


def _load(ep: Episode) -> dict:
    p = ep.dir / FILE
    if p.is_file() or p.with_name(p.name + ".bak").is_file():
        try:
            doc = read_json(p)
            if doc.get("schema") == SCHEMA:
                return doc
        except (OSError, ValueError):
            pass
    return {"schema": SCHEMA, "tracks": {}}


def _save(ep: Episode, doc: dict) -> None:
    atomic_write_json(ep.dir / FILE, doc, protected=tuple(m.path for m in ep.media.values()))


def measurements(ep: Episode) -> dict[str, dict]:
    """Per-track measurements, measured on first use and cached in levels.json."""
    with _lock:
        doc = _load(ep)
        changed = False
        for name in voice_tracks(ep):
            key = _track_key(ep, name)
            if (doc["tracks"].get(name) or {}).get("key") != key:
                doc["tracks"][name] = measure_track(ep, name) | {"key": key, "measured_at": _now()}
                changed = True
        if changed:
            _save(ep, doc)
        return {n: doc["tracks"][n] for n in voice_tracks(ep)}


def plan(meas: dict[str, dict], target: float = TARGET_LUFS) -> dict[str, float]:
    """Gain per track that puts every measured host at the same loudness (see module doc)."""
    want, room = {}, {}
    for name, m in meas.items():
        if m.get("lufs") is None:
            continue
        want[name] = target - m["lufs"]
        loud = m.get("loud_peak_db")
        room[name] = PEAK_CEIL_DB - loud if loud is not None else math.inf
    if not want:
        return {}
    short = min(max(0.0, max(want[n] - room[n] for n in want)), MAX_SHORTFALL)
    return {n: round(min(max(g - short, GAIN_MIN), GAIN_MAX), 1) for n, g in want.items()}


# ===================================================================== gains as edits

def current_gains(ep: Episode) -> dict[str, float]:
    with ep.lock:
        tl = ep.timeline_for(ep.enabled)
        return {t.name: round(t.gain_db, 2) for t in tl.tracks if t.name in voice_tracks(ep)}


def _gain_only(e, track: str) -> bool:
    return bool(e.ops) and all(o["op"] == "track_gain" and o["track"] == track for o in e.ops)


def _title(track: str, gain: float) -> str:
    return tr("{track} 音量 {gain} dB", track=track, gain=f"{gain:+.1f}")


def initial_level(ep: Episode, gains: dict[str, float]) -> None:
    """Gains as part of a new episode's first state (import): applied, no undo step."""
    with ep.lock:
        for track, g in gains.items():
            if abs(g) < 0.05:
                continue
            e = ep.add_edit([{"op": "track_gain", "track": track, "gain_db": g}], "loudness", _title(track, g),
                            tr("导入时自动统一两人音量"), source="level", status=APPLIED)
            e.approved = True
        ep.timeline_for(ep.enabled)
        ep.save()


def set_gains(ep: Episode, gains: dict[str, float], label: str | None = None) -> dict[str, float]:
    """Set track gains (absolute dB) as ONE undoable step; returns what changed."""
    names = set(voice_tracks(ep))
    for t in gains:
        if t not in names:
            raise KeyError(t)
    with ep.lock:
        cur = current_gains(ep)
        changes: list[tuple[str, str, object]] = []
        new: list[str] = []
        done: dict[str, float] = {}
        for track, g in gains.items():
            g = round(min(max(float(g), GAIN_MIN), GAIN_MAX), 1)
            if abs(cur.get(track, 0.0) - g) < 0.05:
                continue
            e = ep.add_edit([{"op": "track_gain", "track": track, "gain_db": g}], "loudness", _title(track, g),
                            source="level", status=PROPOSED)
            new.append(e.id)
            changes += [(e.id, "status", APPLIED), (e.id, "approved", True)]
            changes += [(o.id, "status", DISCARDED) for o in ep.edits.values()
                        if o.status == APPLIED and o.id not in new and _gain_only(o, track)]
            done[track] = g
        if not changes:
            return {}
        if label is None:
            label = "；".join(ep.edits[i].title for i in new)  # i18n-ignore
        try:   # history labels stay Chinese and are translated on display (episode.history_label)
            ep.change(f"应用：{label}", changes)  # i18n-ignore
        except ConflictError:
            for i in new:
                ep.edits.pop(i, None)
            raise
        return done


def auto_level(ep: Episode) -> dict[str, float]:
    """Level an existing episode as one undoable step (「统一两人音量」)."""
    return set_gains(ep, plan(measurements(ep)), tr("统一两人音量"))


def level_new_episode(ep: Episode) -> dict[str, float]:
    """Import: measure and level a freshly created episode."""
    gains = plan(measurements(ep))
    initial_level(ep, gains)
    with _lock:
        doc = _load(ep)
        doc["auto"] = {"gains": gains, "target_lufs": TARGET_LUFS, "at": _now()}
        _save(ep, doc)
    return gains


def view(ep: Episode) -> dict:
    """What the 「声音」 page shows."""
    meas = measurements(ep)
    gains = current_gains(ep)
    suggested = plan(meas)
    with ep.lock:
        cuts = ep.cuts_for(ep.enabled)
    tracks = []
    for name in voice_tracks(ep):
        m = meas.get(name, {})
        g = gains.get(name, 0.0)
        rep = declip.track_report(ep.dir, ep.media, ep.base, name)
        times = []
        for t in rep["skipped_times"]:                        # spots left as recorded
            b = int(round(t * ep.sr))
            if not any(a <= b < e for a, e in cuts):          # still in the cut
                times.append(round(to_tl(b, cuts) / ep.sr, 2))
        tracks.append({"name": name, "gain_db": g, "lufs": m.get("lufs"),
                       "level_lufs": round(m["lufs"] + g, 1) if m.get("lufs") is not None else None,
                       "suggested_gain_db": suggested.get(name), "peak_db": m.get("peak_db"),
                       "loud_peak_db": m.get("loud_peak_db"),
                       "out_peak_db": round(m["loud_peak_db"] + g, 1) if m.get("loud_peak_db") is not None else None,
                       "clip_count": rep["events"], "clip_repaired": rep["repaired"],
                       "clip_kept": len(times), "clip_times": times[:CLIP_TIMES]})
    even = all(t["suggested_gain_db"] is None or abs(t["suggested_gain_db"] - t["gain_db"]) < 0.5 for t in tracks)
    return {"target_lufs": TARGET_LUFS, "tracks": tracks, "even": even,
            "min_db": GAIN_MIN, "max_db": GAIN_MAX}


# ===================================================================== chat: "我的声音太低"

# what Leon may say in the chat (content, not UI text)
_UP = ("太低", "太小", "太轻", "太弱", "偏低", "偏小", "偏轻", "低了", "小了", "轻了", "听不清", "听不见", "大一点", "大点",  # i18n-ignore
       "大一些", "高一点", "高点", "高一些", "响一点", "响点", "响一些", "调高", "调大", "加大", "提高", "放大", "增大",  # i18n-ignore
       "拉高", "拉大", "加一点", "too quiet", "too low", "too soft", "louder", "turn up", "raise")  # i18n-ignore
_DOWN = ("太高", "太大", "太响", "太吵", "太冲", "偏高", "偏大", "偏响", "高了", "大了", "响了", "小一点", "小点", "小一些",  # i18n-ignore
         "低一点", "低点", "低一些", "轻一点", "轻点", "轻一些", "调低", "调小", "减小", "降低", "压低", "拉低", "减一点",  # i18n-ignore
         "too loud", "too high", "quieter", "turn down", "lower")
_EVEN = ("统一", "一致", "一样大", "一样响", "差不多大", "平衡", "拉平", "match", "even out", "balance")  # i18n-ignore
_VOL = re.compile(r"声音|音量|声|嗓门|音轨|volume|level|loud|quiet", re.I)  # i18n-ignore
_NOT = re.compile(r"删|剪|去掉|切掉|拿掉|配乐|音乐|背景|bgm|歌|片头|片尾|间奏|铺底|cut|music|song", re.I)  # i18n-ignore
_SELF = re.compile(r"我|自己|\bmy\b|\bme\b|\bI\b", re.I)  # i18n-ignore
_BOTH = re.compile(r"两个人|两人|俩|都|整体|全部|大家|我们|整集|both|everyone|overall", re.I)  # i18n-ignore
_SMALL = re.compile(r"稍微|稍稍|一点点|一丁点|略|slightly|a bit|a little", re.I)  # i18n-ignore
_NUM = re.compile(r"(\d+(?:\.\d+)?|[一二两三四五六七八九十])\s*(?:个)?\s*(?:dB|db|分贝|DB)")  # i18n-ignore
_CN = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}  # i18n-ignore
# what Leon may say (content, not UI). Hosts' names as dictation writes them; 配 only as "配的", 配乐 is excluded above
ALIASES = {"pei": ("pei", "佩", "裴", "沛", "pay", "配的", "配声"), "leon": ("leon", "里昂", "利昂", "李昂", "莱昂")}  # i18n-ignore


def _direction(text: str) -> int:
    low = text.lower()
    hits = [(low.find(w), len(w), +1) for w in _UP if w in low] + [(low.find(w), len(w), -1) for w in _DOWN if w in low]
    if not hits:
        return 0
    hits.sort(key=lambda h: (h[0], -h[1]))   # first phrase wins; at one spot the longer one ("太低" over "低")
    return hits[0][2]


def _who(text: str, tracks: list[str], me: str | None) -> list[str]:
    low = text.lower()
    named = [t for t in tracks if any(a in low for a in (t.lower(), *ALIASES.get(t.lower(), ())))]
    if named:
        return named
    if _BOTH.search(text):
        return list(tracks)
    if _SELF.search(text) and me in tracks:
        return [me]
    return list(tracks)


def parse_volume(text: str, tracks: list[str], me: str | None = None) -> dict | None:
    """{"tracks": [...], "delta_db": ±x} or {"even": True} for a volume request, else None."""
    if not _VOL.search(text) or _NOT.search(text):
        return None
    low = text.lower()
    if any(w in low for w in _EVEN):
        return {"even": True}
    d = _direction(text)
    if not d:
        return None
    m = _NUM.search(text)
    if m:
        v = m.group(1)
        amount = float(_CN.get(v, v)) if v in _CN or v.replace(".", "", 1).isdigit() else STEP_DB
    else:
        amount = SMALL_STEP_DB if _SMALL.search(text) else STEP_DB
    amount = min(max(amount, 0.5), 12.0)
    return {"tracks": _who(text, tracks, me), "delta_db": d * amount}


def chat_volume(ep: Episode, text: str, playhead: float) -> dict | None:
    """Answer a volume request in the editing chat without the AI; None if it is not one."""
    tracks = voice_tracks(ep)
    req = parse_volume(text, tracks, tracks[0] if tracks else None)
    if req is None:
        return None
    if req.get("even"):
        done = auto_level(ep)
        if done:
            parts = "，".join(f"{t} {g:+.1f} dB" for t, g in done.items())  # i18n-ignore
            reply = tr("好，两人音量已经统一：{parts}。不满意可以点「撤销」，或者到「声音」页细调。", parts=parts)
        else:
            reply = tr("两人音量已经是一致的，不用再调。到「声音」页可以单独细调。")
    else:
        cur = current_gains(ep)
        want = {t: cur.get(t, 0.0) + req["delta_db"] for t in req["tracks"]}
        done = set_gains(ep, want)
        who = "、".join(req["tracks"])  # i18n-ignore
        amt = f"{abs(req['delta_db']):g}"
        if not done:
            reply = tr("{who} 的音量已经到头了（{lo} ~ +{hi} dB），没法再调。", who=who, lo=f"{GAIN_MIN:g}", hi=f"{GAIN_MAX:g}")
        else:
            now_ = "，".join(f"{t} {g:+.1f} dB" for t, g in done.items())  # i18n-ignore
            reply = (tr("好，{who} 的音量调高了 {amt} dB（现在 {now}）。可以点「撤销」退回，或者到「声音」页细调。", who=who, amt=amt, now=now_)
                     if req["delta_db"] > 0 else
                     tr("好，{who} 的音量调低了 {amt} dB（现在 {now}）。可以点「撤销」退回，或者到「声音」页细调。", who=who, amt=amt, now=now_))
    ep.log_turn(text, playhead, reply, volume=True)
    return {"reply": reply, "notes": [], "adapter": "levels", "proposal": None, "usage": None}


# ===================================================================== music

def music_lufs(lib, asset: dict, src_in_s: float, src_out_s: float) -> float | None:
    """Loudness (dual-mono LUFS, the scale of `music.voice_lufs`) of the part of a song that plays."""
    from .library import ANALYSIS_SR
    a_s, b_s = max(0.0, float(src_in_s)), float(src_out_s)
    key = (asset.get("id"), asset.get("sha256"), round(a_s, 2), round(b_s, 2))
    with _lock:
        if key in _music_cache:
            _music_cache.move_to_end(key)
            return _music_cache[key]
    try:
        m = lib.media(asset, ANALYSIS_SR, "m")
        meter = LoudnessMeter(m.sample_rate, 1, dual_mono=True, true_peak=False)
        a, b = int(a_s * m.sample_rate), min(int(b_s * m.sample_rate), m.frames)
        step = int(_BLOCK_S * m.sample_rate)
        with SourcePool({m.media_id: m}) as pool:
            for s in range(a, b, step):
                meter.add(pool.read(m.media_id, s, min(s + step, b)))
        v = meter.integrated()
        # BS.1770 needs 0.4 s: a shorter sting is levelled by the whole song instead of not at all
        out = round(v, 2) if math.isfinite(v) else (asset.get("lufs") if b - a < int(0.4 * m.sample_rate) else None)
    except Exception:      # noqa: BLE001 - a song we cannot read falls back to the library's whole-file value
        out = asset.get("lufs")
    with _lock:
        _music_cache[key] = out
        while len(_music_cache) > 256:
            _music_cache.popitem(last=False)
    return out


def music_level_db(lib, asset: dict, p: dict, voice_lufs: float, level_lu: float) -> float:
    """Automatic gain of a placement: its played part sits `level_lu` from the voice (0 if unmeasurable)."""
    lufs = music_lufs(lib, asset, p.get("src_in_s", 0.0), p.get("src_out_s", asset.get("duration_s", 0.0)))
    if lufs is None:
        return 0.0
    return round(min(max(voice_lufs + level_lu - lufs, -40.0), 30.0), 2)
