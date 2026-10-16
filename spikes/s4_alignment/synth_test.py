#!/usr/bin/env python3
"""Synthetic ground-truth test for align.py.

Builds a fake "final" from a slice of the real raw tracks with a known edit list (joint cuts,
single-track cuts, a backward jump / repeated phrase, a music insert, a music bed under speech,
per-track gains with slow gain wobble), encodes it to MP3 like a real export, runs align.py on it
and scores the recovered edits against the truth.

  python3 -I synth_test.py --leon L.wav --pei P.wav --work DIR [--seed 1]

Writes DIR/synth_final.mp3, DIR/synth_truth.json, DIR/synth_alignment.json, DIR/synth_score.json.
The audio files stay in DIR (keep DIR outside the repo).
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--leon', required=True)
    ap.add_argument('--pei', required=True)
    ap.add_argument('--work', required=True)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--raw-start', type=float, default=1000.0)
    ap.add_argument('--raw-len', type=float, default=480.0)
    ap.add_argument('--cache-dir')
    ap.add_argument('--rescore', action='store_true',
                    help='reuse the existing synth_final.mp3/truth and cached Viterbi paths; rerun analysis + scoring only')
    args = ap.parse_args()
    os.makedirs(args.work, exist_ok=True)
    if args.rescore:
        mp3 = os.path.join(args.work, 'synth_final.mp3')
        truth = json.load(open(os.path.join(args.work, 'synth_truth.json')))
        return run_and_score(args, mp3, truth, analyse_only=True)
    rng = np.random.default_rng(args.seed)
    info = sf.info(args.leon)
    sr = info.samplerate
    a0, a1 = int(args.raw_start * sr), int((args.raw_start + args.raw_len) * sr)
    L = sf.read(args.leon, start=a0, stop=a1, dtype='float32')[0]
    P = sf.read(args.pei, start=a0, stop=a1, dtype='float32')[0]
    if L.ndim > 1:
        L = L.mean(1)
    if P.ndim > 1:
        P = P.mean(1)

    # ---- edit operations applied in FINAL time, like an editor working on a two-track timeline.
    # Each track is a list of [raw_start, raw_end] clips (seconds, relative to the slice).
    def delete(clips, a, b):
        out, t = [], 0.0
        for x, y in clips:
            d = y - x
            s0, s1 = t, t + d               # this clip's span on the timeline
            if s1 <= a or s0 >= b:
                out.append([x, y])
            else:
                if a > s0:
                    out.append([x, x + (a - s0)])
                if b < s1:
                    out.append([x + (b - s0), y])
            t = s1
        return [c for c in out if c[1] - c[0] > 1e-9]

    def length(clips):
        return sum(y - x for x, y in clips)

    def copy_range(clips, a, b):
        out, t = [], 0.0
        for x, y in clips:
            s0, s1 = t, t + (y - x)
            lo, hi = max(a, s0), min(b, s1)
            if hi > lo:
                out.append([x + lo - s0, x + hi - s0])
            t = s1
        return out

    def insert(clips, at, new):
        out, t, done = [], 0.0, False
        for x, y in clips:
            s0, s1 = t, t + (y - x)
            if not done and s0 <= at < s1:
                if at > s0:
                    out.append([x, x + at - s0])
                out.extend([list(c) for c in new])
                out.append([x + at - s0, y])
                done = True
            else:
                out.append([x, y])
            t = s1
        return [c for c in out if c[1] - c[0] > 1e-9]

    kl = [[0.0, args.raw_len]]
    kp = [[0.0, args.raw_len]]
    truth_single = []
    # single-track deletions first (they create inter-track offset changes)
    for track, n in (('Pei', 3), ('Leon', 1)):
        for _ in range(n):
            c0 = rng.uniform(20, length(kl) - 60)
            l = rng.uniform(0.25, 0.9)
            if track == 'Pei':
                kp = delete(kp, c0, c0 + l)
            else:
                kl = delete(kl, c0, c0 + l)
            truth_single.append(dict(track=track, final_time_at_op=c0, len=l))
    # joint deletions (both tracks, same timeline range)
    lens = np.concatenate([rng.uniform(0.12, 0.6, 12), rng.uniform(0.6, 3, 10), rng.uniform(3, 15, 8)])
    rng.shuffle(lens)
    cuts = []
    for l in lens:
        c0 = rng.uniform(3, min(length(kl), length(kp)) - l - 30)
        kl = delete(kl, c0, c0 + l)
        kp = delete(kp, c0, c0 + l)
        cuts.append((c0, l))
    # a repeated phrase: copy 1.2 s of the timeline (both tracks) and paste it 20 s later
    x0 = rng.uniform(30, min(length(kl), length(kp)) - 60)
    nl, npc = copy_range(kl, x0, x0 + 1.2), copy_range(kp, x0, x0 + 1.2)
    kl = insert(kl, x0 + 20, nl)
    kp = insert(kp, x0 + 20, npc)
    rep = [x0, x0 + 1.2]

    def render(X, klist):
        return np.concatenate([X[int(x * sr):int(y * sr)] for x, y in klist])

    Lf, Pf = render(L, kl), render(P, kp)
    n = max(len(Lf), len(Pf))
    Lf = np.pad(Lf, (0, n - len(Lf)))
    Pf = np.pad(Pf, (0, n - len(Pf)))
    t = np.arange(n) / sr
    wob = 10 ** ((1.5 * np.sin(2 * np.pi * t / 23.0)) / 20)
    speech = 2.2 * wob * Lf + 1.0 * wob * Pf

    # music: insert of 10 s at ~40% of the final, plus a quiet bed under 60 s of speech
    def music(dur, level_db):
        m = int(dur * sr)
        tt = np.arange(m) / sr
        sig = np.zeros(m)
        for f0 in (220, 277.2, 329.6, 440):
            sig += np.sin(2 * np.pi * f0 * tt + rng.uniform(0, 6)) * (0.6 + 0.4 * np.sin(2 * np.pi * tt / rng.uniform(1.5, 4)))
        sig += 0.3 * rng.standard_normal(m)
        sig /= np.sqrt(np.mean(sig ** 2))
        env = np.minimum(1, np.minimum(tt / 0.5, (dur - tt) / 0.5))
        return (sig * env * 10 ** (level_db / 20)).astype(np.float32)

    ins_at = int(0.4 * n)
    ins_at_s = ins_at / sr
    ins_dur = 10.0
    final = np.concatenate([speech[:ins_at], music(ins_dur, -20), speech[ins_at:]])
    bed_s, bed_d = 0.7 * len(final) / sr, 60.0
    bed = music(bed_d, -38)
    b0 = int(bed_s * sr)
    final[b0:b0 + len(bed)] += bed[:len(final) - b0]
    final = np.clip(final, -1, 1)

    wav = os.path.join(args.work, 'synth_final.wav')
    mp3 = os.path.join(args.work, 'synth_final.mp3')
    sf.write(wav, final, sr, subtype='PCM_16')
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', wav, '-ac', '2', '-b:a', '128k', mp3], check=True)
    os.remove(wav)

    # ---- truth, in final time; offsets in absolute raw time
    def track_truth(klist):
        segs = []
        ft = 0.0
        for x, y in klist:
            f0, f1 = ft, ft + (y - x)
            # shift for the music insert
            segs.append((f0, f1, x + args.raw_start))
            ft = f1
        out = []
        for f0, f1, rs in segs:
            if f0 < ins_at_s < f1:
                out.append((f0, ins_at_s, rs))
                out.append((ins_at_s + ins_dur, f1 + ins_dur, rs + ins_at_s - f0))
            elif f0 >= ins_at_s:
                out.append((f0 + ins_dur, f1 + ins_dur, rs))
            else:
                out.append((f0, f1, rs))
        sw = []
        for (p0, p1, prs), (q0, q1, qrs) in zip(out[:-1], out[1:]):
            o1, o2 = prs - p0, qrs - q0
            if abs(o2 - o1) > 1e-6:
                sw.append(dict(pos=q0, jump=o2 - o1, across_insert=bool(abs(p1 - q0) > 1e-6)))
        return [dict(final=[a, b], raw=[r, r + b - a]) for a, b, r in out], sw

    segL, swL = track_truth(kl)
    segP, swP = track_truth(kp)
    truth = dict(sr=sr, raw_start=args.raw_start, joint_cuts_timeline_ops=cuts,
                 single_track_ops=truth_single, repeat_timeline=rep,
                 insert=[ins_at_s, ins_at_s + ins_dur], bed=[bed_s, bed_s + bed_d],
                 switches=dict(Leon=swL, Pei=swP), segments=dict(Leon=segL, Pei=segP))
    json.dump(truth, open(os.path.join(args.work, 'synth_truth.json'), 'w'), indent=1, default=float)
    run_and_score(args, mp3, truth)


def run_and_score(args, mp3, truth, analyse_only=False):
    out = os.path.join(args.work, 'synth_alignment.json')
    cmd = [sys.executable, '-I', os.path.join(HERE, 'align.py'), '--leon', args.leon, '--pei', args.pei,
           '--final', mp3, '--out', out, '--no-insert-probe']
    if args.cache_dir:
        cmd += ['--cache-dir', args.cache_dir]
    if analyse_only:
        cmd += ['--analyse-only']
    subprocess.run(cmd, check=True)
    score = score_alignment(json.load(open(out)), truth)
    json.dump(score, open(os.path.join(args.work, 'synth_score.json'), 'w'), indent=1, default=float)
    print(json.dumps(score['summary'], indent=1))


def score_alignment(res, truth):
    """Per-track switch matching: detected (pos, jump) vs truth."""
    det = {'Leon': [], 'Pei': []}
    for e in res['edit_events']:
        for tr in e['tracks']:
            jump = e['jump_by_track'][tr] if 'jump_by_track' in e else e['jump_s']
            det[tr].append(dict(pos=e['final_pos'], jump=jump, kind=e['kind'], amb=e['ambiguity'],
                                hb=e.get('heard_bounds', e['ambiguity']), conf=e['confidence']))
    summary = {}
    details = {}
    for tr in ('Leon', 'Pei'):
        tsw = [s for s in truth['switches'][tr] if not s['across_insert']]
        used = set()
        errs, matched = [], []
        for s in tsw:
            best = None
            for k, d in enumerate(det[tr]):
                if k in used or abs(d['jump'] - s['jump']) > 0.005:
                    continue
                near = abs(d['pos'] - s['pos']) < 1.0 or (d['hb'][0] - 0.01 <= s['pos'] <= d['hb'][1] + 0.01)
                if near and (best is None or abs(d['pos'] - s['pos']) < abs(det[tr][best]['pos'] - s['pos'])):
                    best = k
            if best is not None:
                used.add(best)
                d = det[tr][best]
                errs.append(d['pos'] - s['pos'])
                matched.append(dict(truth_pos=round(s['pos'], 4), det_pos=d['pos'], err_ms=round((d['pos'] - s['pos']) * 1000, 1),
                                    jump=round(s['jump'], 4), in_ambiguity=bool(d['amb'][0] - 0.001 <= s['pos'] <= d['amb'][1] + 0.001),
                                    in_heard_bounds=bool(d['hb'][0] - 0.01 <= s['pos'] <= d['hb'][1] + 0.01),
                                    kind=d['kind'], conf=d['conf']))
            else:
                matched.append(dict(truth_pos=round(s['pos'], 4), jump=round(s['jump'], 4), missed=True))
        # insert-adjacent detections are not false positives
        ins = truth['insert']
        fp = [d for k, d in enumerate(det[tr]) if k not in used and not (ins[0] - 1.5 <= d['pos'] <= ins[1] + 1.5)]
        e = np.abs(np.array(errs)) * 1000 if errs else np.array([np.nan])
        summary[tr] = dict(truth_switches=len(tsw), detected=len(errs), false_positives=len(fp),
                           abs_err_ms_median=round(float(np.median(e)), 1), abs_err_ms_p90=round(float(np.percentile(e, 90)), 1),
                           abs_err_ms_max=round(float(np.max(e)), 1),
                           within_20ms=int(np.sum(e <= 20)), within_5ms=int(np.sum(e <= 5)),
                           truth_inside_heard_bounds=sum(1 for m in matched if m.get('in_heard_bounds')), truth_inside_reported_ambiguity=sum(1 for m in matched if m.get('in_ambiguity')))
        details[tr] = dict(matched=matched, false_positives=fp)
    # offset correctness over time: fraction of raw-derived final time where the detected
    # per-track offset equals the true one (within 1 ms)
    for tr, key in (('Leon', 'offset_leon'), ('Pei', 'offset_pei')):
        tsegs = truth['segments'][tr]
        dsegs = [x for x in res['segments'] if x['type'] == 'raw']
        grid = np.arange(0, res['stats']['final_duration_s'], 0.01)
        tof = np.full(len(grid), np.nan)
        for g in tsegs:
            m = (grid >= g['final'][0]) & (grid < g['final'][1])
            tof[m] = g['raw'][0] - g['final'][0]
        dof = np.full(len(grid), np.nan)
        heard = np.zeros(len(grid), bool)
        for g in dsegs:
            m = (grid >= g['final_start']) & (grid < g['final_end'])
            dof[m] = g[key]
            heard[m] = g['evidence_s'][tr] >= 0.1
        ok = ~np.isnan(tof)
        good = ok & (np.abs(dof - tof) < 0.001)
        summary[tr]['offset_correct_time_frac'] = round(float(good.sum() / ok.sum()), 4)
        summary[tr]['offset_wrong_s'] = round(float((ok & ~good).sum() * 0.01), 2)
        okh = ok & heard
        summary[tr]['offset_correct_frac_where_track_heard'] = round(float((good & heard).sum() / max(okh.sum(), 1)), 4)
        summary[tr]['offset_wrong_s_where_track_heard'] = round(float((okh & ~good).sum() * 0.01), 2)
    ins_det = res['inserts']
    summary['insert_truth'] = [round(x, 3) for x in truth['insert']]
    summary['insert_detected'] = [[s['final_start'], s['final_end']] for s in ins_det]
    summary['validation_global_ncc'] = res['validation']['segment_gain']['global_ncc']
    summary['single_track_truth'] = truth['single_track_ops']
    summary['single_events_detected'] = [dict(track=e['tracks'], pos=e['final_pos'], jump=e['jump_s'], raw=e.get('raw'), conf=e['confidence'])
                                         for e in res['edit_events'] if e['kind'] == 'single']
    return dict(summary=summary, details=details)


if __name__ == '__main__':
    main()
