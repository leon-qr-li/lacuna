#!/usr/bin/env python3
"""S4 spike: reconstruct a manual podcast edit by aligning the final mix to the raw per-host tracks.

Model
-----
final(t) ~= gL(t) * Leon(t + oL(t)) + gP(t) * Pei(t + oP(t)) + other(t)

oL(t), oP(t) are piecewise-constant per-track offsets (raw = final + offset). Normally oL == oP
(a cut made on both tracks at once); oL != oP means a single-track edit (one track cut/slid
relative to the other). `other` is non-raw material (music, clips) and processing residue.

Pipeline (all at 8 kHz mono, waveform domain):
  1. mix anchors: 1 s windows of the final (hop 0.5 s) -> best NCC lag in Leon+Pei
     (predicted lag first, then a local window, then a decimated global search).
  2. per-track anchors: 0.5 s windows (hop 0.25 s) -> best NCC lag in each track alone,
     searched within +-6 s of nearby mix anchors. Offsets of all anchors become candidates.
  3. joint Viterbi over (oL, oP) candidate pairs on 10 ms frames. Emission = 1 - (explained
     energy of final by Leon@oL + by Pei@oP), each from a 150 ms smoothed single-gain LS fit.
     Transition penalty: both tracks switch together = LAMBDA_JOINT, one track = LAMBDA_SINGLE.
  4. discovery pass: poorly explained speech spans are re-searched with short queries; new
     candidates are added and the Viterbi is rerun.
  5. sample-level refinement of every switch (cumulative squared error of the two hypotheses,
     other track's contribution subtracted) + ambiguity interval (frames where the two
     hypotheses are indistinguishable, e.g. a cut inside a pause).
  6. segments, removed raw spans (joint / single-track), backward jumps (moves/repeats),
     non-raw inserts, muted-track spans, per-segment gains, validation by reconstruction.

Usage:
  python3 -I align.py --leon L.wav --pei P.wav --final final.mp3 --out out/ep.json \
      [--cache-dir DIR]

Inputs are only read. Decoded 8 kHz float32 copies and intermediate anchor results are cached in
--cache-dir (default: ./cache next to --out).
"""
import argparse
import json
import os
import subprocess
import sys
import time

import numpy as np
from scipy.signal import oaconvolve, resample_poly

SR = 8000
HOP = 80                 # 10 ms frames
SMOOTH_H = 7             # +-7 frames (150 ms) for local gains / explained energy
LAMBDA_JOINT = 3.0
LAMBDA_SINGLE = 8.0
CHUNK_FR = 2000          # Viterbi chunk (20 s) for local candidate sets
CAND_CTX_S = 12.0        # candidates from anchors within +-12 s of a chunk


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, file=sys.stderr, flush=True)


# ----------------------------------------------------------------------------- io
def load_audio(path, cache_dir):
    os.makedirs(cache_dir, exist_ok=True)
    st = os.stat(path)
    key = '%s_%d_%d.f32' % (os.path.basename(path).encode('utf-8').hex()[:40], st.st_size, int(st.st_mtime))
    cp = os.path.join(cache_dir, key)
    if not os.path.exists(cp):
        log('decoding', path)
        cmd = ['ffmpeg', '-v', 'error', '-nostdin', '-i', path, '-ac', '1', '-ar', str(SR), '-f', 'f32le', cp + '.tmp']
        subprocess.run(cmd, check=True)
        os.replace(cp + '.tmp', cp)
    return np.fromfile(cp, np.float32)


# ----------------------------------------------------------------------------- matching
class Searcher:
    """Normalized cross-correlation search of a query inside a long reference."""

    def __init__(self, ref, decim=4):
        self.ref = ref
        self.c2 = np.concatenate([[0.0], np.cumsum(ref.astype(np.float64) ** 2)])
        self.decim = decim
        self.refd = resample_poly(ref, 1, decim).astype(np.float32)
        self.c2d = np.concatenate([[0.0], np.cumsum(self.refd.astype(np.float64) ** 2)])

    @staticmethod
    def _ncc(ref, c2, q, lo, hi):
        lo = max(lo, 0)
        hi = min(hi, len(ref) - len(q))
        if hi <= lo:
            return None
        seg = ref[lo:hi + len(q)]
        qz = q - q.mean()
        qn = np.linalg.norm(qz) + 1e-9
        c = oaconvolve(seg, qz[::-1], 'valid')
        e = c2[lo + len(q):hi + len(q) + 1] - c2[lo:hi + 1]
        c = c / (np.sqrt(np.maximum(e, 1e-12)) * qn)
        return lo, c

    def search(self, q, lo, hi):
        r = self._ncc(self.ref, self.c2, q, lo, hi)
        if r is None:
            return -1, 0.0
        lo, c = r
        i = int(np.argmax(c))
        return lo + i, float(c[i])

    def search_global(self, q, topk=4):
        d = self.decim
        qd = resample_poly(q, 1, d).astype(np.float32)
        lo, c = self._ncc(self.refd, self.c2d, qd, 0, len(self.refd))
        best = (-1, 0.0)
        cc = c.copy()
        for _ in range(topk):
            i = int(np.argmax(cc))
            if cc[i] <= 0:
                break
            j, v = self.search(q, (lo + i) * d - 3 * d, (lo + i) * d + 3 * d)
            if v > best[1]:
                best = (j, v)
            cc[max(0, i - SR // d):i + SR // d] = -1
        return best


def rms(x):
    return float(np.sqrt(np.mean(x.astype(np.float64) ** 2))) if len(x) else 0.0


def mix_anchors(F, mix_s, W=1.0, H=0.5, thr=0.5):
    w, h = int(W * SR), int(H * SR)
    out = []
    o = None
    recent = []
    insert_mode = 0
    nwin = (len(F) - w) // h
    t0 = time.time()
    for k in range(nwin):
        t = k * h
        q = F[t:t + w]
        if rms(q) < 10 ** (-55 / 20):
            out.append((t, 0, 0.0, 0))
            continue
        best, how = (-1, 0.0), 0
        for oc in ([o] if o is not None else []) + recent[-8:][::-1]:
            i, c = mix_s.search(q, t + oc - 80, t + oc + 80)
            if c > best[1]:
                best, how = (i, c), 1
            if c > 0.6:
                break
        if best[1] < 0.6 and o is not None:
            i, c = mix_s.search(q, t + o - 30 * SR, t + o + 150 * SR)
            if c > best[1]:
                best, how = (i, c), 2
        if best[1] < thr and (insert_mode == 0 or k % 4 == 0):
            i, c = mix_s.search_global(q)
            if c > best[1]:
                best, how = (i, c), 3
        i, c = best
        if c >= thr:
            o = i - t
            insert_mode = 0
            if o not in recent:
                recent.append(o)
        else:
            insert_mode = 1
        out.append((t, (i - t) if i >= 0 else 0, c, how))
        if k % 1000 == 0:
            log('mix anchors %d/%d %.0fs' % (k, nwin, time.time() - t0))
    return np.array(out, dtype=np.float64)


def track_anchors(F, X, xs, manch, W=0.5, H=0.25, rad=6.0, thr=0.6):
    """Per-track anchors around nearby mix-anchor offsets."""
    w, h = int(W * SR), int(H * SR)
    good = manch[manch[:, 2] >= 0.5]
    gt, go = good[:, 0], good[:, 1].astype(np.int64)
    # track noise floor (frame rms 10th pct)
    fr = np.sqrt(np.mean(X[:len(X) // 4000 * 4000].reshape(-1, 4000).astype(np.float64) ** 2, 1))
    floor = np.percentile(fr, 10)
    out = []
    nwin = (len(F) - w) // h
    for k in range(nwin):
        t = k * h
        q = F[t:t + w]
        sel = np.abs(gt - t) < 4 * SR
        offs = np.unique(go[sel]) if sel.any() else go[np.argsort(np.abs(gt - t))[:3]]
        # cluster offsets to limit searches
        offs_c = []
        for v in np.sort(offs):
            if not offs_c or v - offs_c[-1] > rad * SR:
                offs_c.append(v)
        best = (-1, 0.0)
        for oc in offs_c:
            i, c = xs.search(q, t + oc - int(rad * SR), t + oc + int(rad * SR))
            if c > best[1]:
                best = (i, c)
        i, c = best
        if i >= 0 and c >= thr and rms(X[i:i + w]) > floor * 3:
            out.append((t, i - t, c))
    return np.array(out, dtype=np.float64).reshape(-1, 3)


# ----------------------------------------------------------------------------- frame features
def frame_sums(a, b):
    n = len(a) // HOP * HOP
    return np.einsum('ij,ij->i', a[:n].reshape(-1, HOP).astype(np.float64), b[:n].reshape(-1, HOP).astype(np.float64))


def shifted(X, start, n):
    """X[start:start+n] with zero padding outside."""
    out = np.zeros(n, np.float32)
    a, b = max(start, 0), min(start + n, len(X))
    if b > a:
        out[a - start:b - start] = X[a:b]
    return out


def box(x, h=SMOOTH_H):
    k = np.ones(2 * h + 1)
    return np.convolve(x, k, 'same')


class FrameModel:
    def __init__(self, F, tracks):
        self.F = F
        self.tracks = tracks
        self.nfr = len(F) // HOP
        self.FF = frame_sums(F, F)
        self.FFs = box(self.FF)
        self.floorF = float(np.percentile(self.FFs, 10))

    def track_feats(self, ti, off, f0, f1):
        """per-frame FX, XX for track ti at offset off for frames [f0,f1) (+ smoothing pad)."""
        p = SMOOTH_H
        g0, g1 = max(f0 - p, 0), min(f1 + p, self.nfr)
        n = (g1 - g0) * HOP
        x = shifted(self.tracks[ti], g0 * HOP + off, n)
        f = self.F[g0 * HOP:g0 * HOP + n]
        FX = frame_sums(f, x)
        XX = frame_sums(x, x)
        FXs, XXs = box(FX), box(XX)
        sl = slice(f0 - g0, f1 - g0)
        return FX[sl], XX[sl], FXs[sl], XXs[sl]

    def explained(self, ti, off, f0, f1):
        FX, XX, FXs, XXs = self.track_feats(ti, off, f0, f1)
        e = np.clip(FXs, 0, None) ** 2 / (XXs * (self.FFs[f0:f1] + self.floorF) + 1e-20)
        return np.clip(e, 0, 1), FXs / (XXs + 1e-20)


# ----------------------------------------------------------------------------- candidates
def cluster_offsets(anch_t, anch_o, anch_c, tol=2):
    """Group anchor offsets (samples) into candidate offsets; returns list of (offset, times, cs)."""
    order = np.argsort(anch_o)
    cands = []
    for i in order:
        o = anch_o[i]
        if cands and o - cands[-1]['last'] <= tol:
            c = cands[-1]
        else:
            c = {'offs': [], 't': [], 'c': [], 'last': o}
            cands.append(c)
        c['offs'].append(o); c['t'].append(anch_t[i]); c['c'].append(anch_c[i]); c['last'] = o
    res = []
    for c in cands:
        offs = np.array(c['offs'])
        vals, cnt = np.unique(offs, return_counts=True)
        res.append((int(vals[np.argmax(cnt)]), np.array(c['t']), np.array(c['c'])))
    return res


def local_sets(cands, nfr):
    """For every chunk, the candidate indices with an anchor within CAND_CTX_S."""
    nch = (nfr + CHUNK_FR - 1) // CHUNK_FR
    sets = []
    for k in range(nch):
        a = k * CHUNK_FR * HOP - CAND_CTX_S * SR
        b = (k + 1) * CHUNK_FR * HOP + CAND_CTX_S * SR
        s = [i for i, (o, t, c) in enumerate(cands) if np.any((t >= a) & (t <= b))]
        sets.append(s)
    return sets


# ----------------------------------------------------------------------------- viterbi
def joint_viterbi(fm, candL, candP, setsL, setsP):
    nfr = fm.nfr
    nch = len(setsL)
    BIG = 1e18
    S = None
    prevL = prevP = None
    back = []      # per chunk: (sL, sP, codes[nf,KL,KP], colarg[nf,KP], rowarg[nf,KL], garg[nf])
    explL_all = {}
    explP_all = {}
    for k in range(nch):
        f0, f1 = k * CHUNK_FR, min((k + 1) * CHUNK_FR, nfr)
        sL = setsL[k] or (prevL if prevL else [0])
        sP = setsP[k] or (prevP if prevP else [0])
        EL = np.stack([fm.explained(0, candL[i][0], f0, f1)[0] for i in sL])   # KL x nf
        EP = np.stack([fm.explained(1, candP[j][0], f0, f1)[0] for j in sP])
        for ii, i in enumerate(sL):
            explL_all[(k, i)] = EL[ii]
        for jj, j in enumerate(sP):
            explP_all[(k, j)] = EP[jj]
        KL, KP, nf = len(sL), len(sP), f1 - f0
        codes = np.zeros((nf, KL, KP), np.int8)
        colarg = np.zeros((nf, KP), np.int32)
        rowarg = np.zeros((nf, KL), np.int32)
        garg = np.zeros((nf, 2), np.int32)
        for fi in range(nf):
            cost = 1.0 - np.minimum(EL[:, fi][:, None] + EP[:, fi][None, :], 1.0)
            if S is None:
                S = cost.copy()
                codes[fi] = 0
                prevL, prevP = sL, sP
                continue
            if fi == 0:
                # map previous chunk's state space into this one
                mapL = np.array([prevL.index(i) if i in prevL else -1 for i in sL])
                mapP = np.array([prevP.index(j) if j in prevP else -1 for j in sP])
            else:
                mapL = np.arange(KL)
                mapP = np.arange(KP)
            colmin_old = S.min(0); colarg_old = S.argmin(0)      # per old P column: best old L
            rowmin_old = S.min(1); rowarg_old = S.argmin(1)      # per old L row: best old P
            g = int(np.argmin(S)); gmin = S.flat[g]
            gi, gj = divmod(g, S.shape[1])
            stay = np.full((KL, KP), BIG)
            vl, vp = mapL >= 0, mapP >= 0
            if vl.any() and vp.any():
                stay[np.ix_(vl, vp)] = S[np.ix_(mapL[vl], mapP[vp])]
            chL = np.full((KL, KP), BIG)          # L changes, P stays
            if vp.any():
                chL[:, vp] = (colmin_old[mapP[vp]] + LAMBDA_SINGLE)[None, :]
            chP = np.full((KL, KP), BIG)          # P changes, L stays
            if vl.any():
                chP[vl, :] = (rowmin_old[mapL[vl]] + LAMBDA_SINGLE)[:, None]
            both = gmin + LAMBDA_JOINT
            allc = np.stack([stay, chL, chP, np.full((KL, KP), both)])
            code = np.argmin(allc, 0)
            S = allc.min(0) + cost
            S -= S.min()
            codes[fi] = code
            colarg[fi, vp] = colarg_old[mapP[vp]]
            rowarg[fi, vl] = rowarg_old[mapL[vl]]
            garg[fi] = (gi, gj)
            if fi == 0:
                back_map = (mapL, mapP)
        back.append((sL, sP, codes, colarg, rowarg, garg, back_map if k > 0 else (np.arange(KL), np.arange(KP))))
        prevL, prevP = sL, sP
        log('viterbi chunk %d/%d KL=%d KP=%d' % (k + 1, nch, KL, KP))
    # backtrack
    pathL = np.zeros(nfr, np.int32)
    pathP = np.zeros(nfr, np.int32)
    i, j = np.unravel_index(int(np.argmin(S)), S.shape)
    for k in range(nch - 1, -1, -1):
        sL, sP, codes, colarg, rowarg, garg, (mapL0, mapP0) = back[k]
        f0 = k * CHUNK_FR
        for fi in range(codes.shape[0] - 1, -1, -1):
            pathL[f0 + fi] = sL[i]
            pathP[f0 + fi] = sP[j]
            if k == 0 and fi == 0:
                break
            c = codes[fi, i, j]
            mL = mapL0 if fi == 0 else np.arange(len(sL))
            mP = mapP0 if fi == 0 else np.arange(len(sP))
            if c == 0:
                ni, nj = mL[i], mP[j]
            elif c == 1:
                ni, nj = colarg[fi, j], mP[j]
            elif c == 2:
                ni, nj = mL[i], rowarg[fi, i]
            else:
                ni, nj = garg[fi]
            i, j = int(ni), int(nj)
    return pathL, pathP


def path_explained(fm, ti, cands, path):
    """explained fraction and local gain along a decoded path."""
    nfr = fm.nfr
    E = np.zeros(nfr)
    G = np.zeros(nfr)
    runs = runs_of(path)
    for a, b, v in runs:
        e, g = fm.explained(ti, cands[v][0], a, b)
        E[a:b], G[a:b] = e, g
    return E, G


def runs_of(path):
    ch = np.flatnonzero(np.diff(path)) + 1
    st = np.concatenate([[0], ch])
    en = np.concatenate([ch, [len(path)]])
    return [(int(a), int(b), int(path[a])) for a, b in zip(st, en)]


# ----------------------------------------------------------------------------- discovery
def discover(F, fm, searchers, EL, EP, offL, offP, max_spans=400):
    """Short-query search for poorly explained speech spans. Returns new anchors per track."""
    tot = EL + EP
    loud = fm.FFs > fm.floorF * 30
    bad = loud & (tot < 0.35)
    spans = []
    for a, b, v in runs_of(bad.astype(np.int32)):
        if v and 12 <= b - a <= 400:
            spans.append((a, b))
    log('discovery spans', len(spans))
    new = {0: [], 1: [], 'mix': []}
    for a, b in spans[:max_spans]:
        t = a * HOP
        n = min((b - a) * HOP, SR)
        q = F[t:t + n]
        for key, s in (('mix', searchers['mix']), (0, searchers[0]), (1, searchers[1])):
            o = offL[a] if key != 1 else offP[a]
            i, c = s.search(q, t + o - 60 * SR, t + o + 60 * SR)
            if c >= 0.6:
                new[key].append((t, i - t, c))
    return new


# ----------------------------------------------------------------------------- refinement
def refine_switch(F, Xs, Ys, oX1, oX2, oY, gX1, gX2, gY, fsw, rad_fr=25):
    """Sample-precise switch time for track X from offset oX1 to oX2 near frame fsw."""
    a = max((fsw - rad_fr) * HOP, 0)
    b = min((fsw + rad_fr) * HOP, len(F))
    n = b - a
    f = F[a:b].astype(np.float64)
    r = f - gY * shifted(Ys, a + oY, n)
    e1 = (r - gX1 * shifted(Xs, a + oX1, n)) ** 2
    e2 = (r - gX2 * shifted(Xs, a + oX2, n)) ** 2
    c = np.concatenate([[0], np.cumsum(e1)]) + (np.sum(e2) - np.concatenate([[0], np.cumsum(e2)]))
    k = int(np.argmin(c))
    # ambiguity: per-10ms frame discriminability; contiguous indistinguishable frames around k
    nf = n // HOP
    d1 = e1[:nf * HOP].reshape(nf, HOP).sum(1)
    d2 = e2[:nf * HOP].reshape(nf, HOP).sum(1)
    ff = (f[:nf * HOP] ** 2).reshape(nf, HOP).sum(1)
    disc = np.abs(d1 - d2) / (ff + d1 + d2 + 1e-12)
    kf = min(k // HOP, nf - 1)
    lo = kf
    while lo > 0 and disc[lo - 1] < 0.15:
        lo -= 1
    hi = kf
    while hi < nf - 1 and disc[hi + 1] < 0.15:
        hi += 1
    # evidence: how much better the chosen split is than the best of the two "no switch" options
    gain = float(min(c[0], c[-1]) - c[k]) / (float(np.sum(f ** 2)) + 1e-12)
    return a + k, a + lo * HOP, a + (hi + 1) * HOP, gain


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--leon', required=True)
    ap.add_argument('--pei', required=True)
    ap.add_argument('--final', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--cache-dir')
    ap.add_argument('--names', nargs=2, default=['Leon', 'Pei'])
    ap.add_argument('--analyse-only', action='store_true', help='reuse cached Viterbi paths')
    ap.add_argument('--no-insert-probe', action='store_true', help='skip global search inside inserts')
    args = ap.parse_args()
    cache = args.cache_dir or os.path.join(os.path.dirname(os.path.abspath(args.out)), 'cache')
    os.makedirs(cache, exist_ok=True)

    L = load_audio(args.leon, cache)
    P = load_audio(args.pei, cache)
    F = load_audio(args.final, cache)
    n = min(len(L), len(P))
    L, P = L[:n], P[:n]
    M = L + P
    log('durations raw %.1fs final %.1fs' % (n / SR, len(F) / SR))
    S = {'mix': Searcher(M), 0: Searcher(L), 1: Searcher(P)}

    ap_path = os.path.join(cache, 'anchors_%d_%d.npz' % (n, len(F)))
    if os.path.exists(ap_path):
        z = np.load(ap_path)
        manch, aL, aP = z['manch'], z['aL'], z['aP']
    else:
        manch = mix_anchors(F, S['mix'])
        log('track anchors')
        aL = track_anchors(F, L, S[0], manch)
        aP = track_anchors(F, P, S[1], manch)
        np.savez(ap_path, manch=manch, aL=aL, aP=aP)
    log('anchors: mix %d (>=0.5: %d), L %d, P %d' % (len(manch), int((manch[:, 2] >= 0.5).sum()), len(aL), len(aP)))

    fm = FrameModel(F, [L, P])
    pp = os.path.join(cache, 'paths_%d_%d.npz' % (n, len(F)))
    if args.analyse_only and os.path.exists(pp):
        z = np.load(pp)
        result = analyse(F, L, P, fm, z['offL'], z['offP'], z['EL'], z['EP'], z['GL'], z['GP'], args, S)
        write_json(result, args.out)
        return
    good = manch[manch[:, 2] >= 0.5]
    # candidates: per-track anchors + mix anchors (mix offset applies to both tracks)
    def build(extra=None):
        allL = [aL, good[:, :3]] + ([np.array(extra[0]).reshape(-1, 3)] if extra else [])
        allP = [aP, good[:, :3]] + ([np.array(extra[1]).reshape(-1, 3)] if extra else [])
        if extra and extra['mix']:
            allL.append(np.array(extra['mix']).reshape(-1, 3)); allP.append(np.array(extra['mix']).reshape(-1, 3))
        # one shared candidate list: an offset seen on either track (or the mix) is a candidate
        # for both, so that a joint cut can always be represented as (o, o).
        A = np.concatenate(allL + allP)
        c = cluster_offsets(A[:, 0], A[:, 1].astype(np.int64), A[:, 2])
        return c, c

    candL, candP = build()
    log('candidates L %d P %d' % (len(candL), len(candP)))
    pathL, pathP = joint_viterbi(fm, candL, candP, local_sets(candL, fm.nfr), local_sets(candP, fm.nfr))
    offL = np.array([candL[i][0] for i in pathL]); offP = np.array([candP[i][0] for i in pathP])
    EL, GL = path_explained(fm, 0, candL, pathL)
    EP, GP = path_explained(fm, 1, candP, pathP)

    disc_path = os.path.join(cache, 'discover_%d_%d.json' % (n, len(F)))
    if os.path.exists(disc_path):
        extra = {int(k) if k != 'mix' else k: v for k, v in json.load(open(disc_path)).items()}
    else:
        extra = discover(F, fm, S, EL, EP, offL, offP)
        json.dump({str(k): v for k, v in extra.items()}, open(disc_path, 'w'))
    log('discovered L %d P %d mix %d' % (len(extra[0]), len(extra[1]), len(extra['mix'])))
    candL, candP = build(extra)
    log('candidates L %d P %d' % (len(candL), len(candP)))
    pathL, pathP = joint_viterbi(fm, candL, candP, local_sets(candL, fm.nfr), local_sets(candP, fm.nfr))
    offL = np.array([candL[i][0] for i in pathL]); offP = np.array([candP[i][0] for i in pathP])
    EL, GL = path_explained(fm, 0, candL, pathL)
    EP, GP = path_explained(fm, 1, candP, pathP)
    np.savez(pp, offL=offL, offP=offP, EL=EL, EP=EP, GL=GL, GP=GP)
    result = analyse(F, L, P, fm, offL, offP, EL, EP, GL, GP, args, S)
    write_json(result, args.out)


def write_json(result, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w') as fh:
        json.dump(result, fh, indent=1, ensure_ascii=False)
    log('wrote', path)




# ----------------------------------------------------------------------------- analysis
INSERT_SMOOTH_FR = 100   # 1 s
INSERT_THR = 0.05        # smoothed explained-energy fraction below which material is non-raw
EVID_THR = 0.5           # per-frame explained fraction that counts as "this track is heard here"


def find_inserts(tot):
    ts = np.convolve(tot, np.ones(INSERT_SMOOTH_FR) / INSERT_SMOOTH_FR, 'same')
    spans = []
    for a, b, v in runs_of((ts < INSERT_THR).astype(np.int32)):
        if v and b - a >= INSERT_SMOOTH_FR:
            # snap edges to the last / first frame where raw speech is clearly heard
            lo = max(a - INSERT_SMOOTH_FR, 0)
            ev = np.flatnonzero(tot[lo:a + INSERT_SMOOTH_FR] > 0.3)
            a2 = lo + ev[-1] + 1 if len(ev) and lo + ev[-1] + 1 <= b else a
            if a == 0 or a2 > b:
                a2 = a
            hi = min(b + INSERT_SMOOTH_FR, len(tot))
            ev = np.flatnonzero(tot[b - INSERT_SMOOTH_FR:hi] > 0.3)
            b2 = b - INSERT_SMOOTH_FR + ev[0] if len(ev) and b - INSERT_SMOOTH_FR + ev[0] >= a2 else b
            spans.append((a2 if a > 0 else 0, b2 if b < len(tot) else len(tot)))
    return spans


def evidence_s(E, a, b):
    a, b = max(a, 0), min(b, len(E))
    return float(np.sum(E[a:b] > EVID_THR)) * HOP / SR if b > a else 0.0


def track_conf(E, a, b):
    ev = evidence_s(E, a, b)
    m = E[a:b] > EVID_THR
    q = float(np.mean(E[a:b][m])) if m.any() else 0.0
    if ev >= 0.3 and q >= 0.7:
        return 'high', ev
    if ev >= 0.1:
        return 'medium', ev
    if ev > 0:
        return 'low', ev
    return 'inferred', ev


def analyse(F, L, P, fm, offL, offP, EL, EP, GL, GP, args, S):
    nfr = fm.nfr
    names = args.names
    Ts = lambda s: round(float(s) / SR, 4)
    Tf = lambda f: round(float(f) * HOP / SR, 4)
    tot = EL + EP

    # ---------------- non-raw inserts
    ins = find_inserts(tot)
    ins_frames = np.zeros(nfr, bool)
    for a, b in ins:
        ins_frames[a:b] = True
    log('inserts', [(Tf(a), Tf(b)) for a, b in ins])

    # ---------------- per-track switches (outside inserts), sample-refined
    tr = {0: (L, P, offL, offP, GL, GP, EL), 1: (P, L, offP, offL, GP, GL, EP)}
    sw = {0: [], 1: []}
    for ti, (X, Y, oX, oY, gX, gY, EX) in tr.items():
        for f in np.flatnonzero(np.diff(oX)) + 1:
            if ins_frames[max(f - 2, 0):f + 2].all():
                continue
            o1, o2 = int(oX[f - 1]), int(oX[f])
            w1 = slice(max(f - 30, 0), f)
            w2 = slice(f, min(f + 30, nfr))
            g1 = float(np.median(gX[w1])) if EX[w1].max() > 0.2 else float(np.median(gX[EX > 0.5][:1000]))
            g2 = float(np.median(gX[w2])) if EX[w2].max() > 0.2 else g1
            gy = float(np.median(gY[max(f - 30, 0):f + 30]))
            pos, lo, hi, gain = refine_switch(F, X, Y, o1, o2, int(oY[f]), g1, g2, gy, f)
            sw[ti].append(dict(f=int(f), pos=pos, lo=lo, hi=hi, o1=o1, o2=o2, jump=o2 - o1, gain=gain,
                               ev_before=evidence_s(EX, f - 300, f), ev_after=evidence_s(EX, f, f + 300)))

    # ---------------- pair L/P switches with the same jump into joint events
    events = []
    usedP = set()
    for s in sw[0]:
        best, bd = None, None
        for k, p in enumerate(sw[1]):
            if k in usedP or abs(p['jump'] - s['jump']) > 3:
                continue
            d = abs(p['pos'] - s['pos'])
            overlap = p['lo'] <= s['hi'] and s['lo'] <= p['hi']
            if d <= 0.6 * SR or overlap:
                if bd is None or d < bd:
                    best, bd = k, d
        if best is None:
            events.append(dict(kind='single', track=0, sw=[s]))
        else:
            usedP.add(best)
            events.append(dict(kind='joint', track=None, sw=[s, sw[1][best]]))
    for k, p in enumerate(sw[1]):
        if k not in usedP:
            events.append(dict(kind='single', track=1, sw=[p]))

    ev_out = []
    for e in events:
        if e['kind'] == 'joint':
            s, p = e['sw']
            ws, wp = s['hi'] - s['lo'], p['hi'] - p['lo']
            # position: from the track that is heard around the cut (narrower ambiguity)
            b = s if ws <= wp else p
            lo, hi = max(s['lo'], p['lo']), min(s['hi'], p['hi'])
            if hi <= lo:
                lo, hi = b['lo'], b['hi']
            pos = min(max(b['pos'], lo), hi)
            jump = b['jump']
            rec = dict(kind='joint', tracks=names[:], final_pos=Ts(pos), ambiguity=[Ts(lo), Ts(hi)],
                       ambiguity_ms=round((hi - lo) / SR * 1000, 1), jump_s=Ts(jump),
                       pos_disagreement_ms=round(abs(s['pos'] - p['pos']) / SR * 1000, 1),
                       raw_leon=[Ts(pos + s['o1']), Ts(pos + s['o2'])], raw_pei=[Ts(pos + p['o1']), Ts(pos + p['o2'])],
                       evidence_s={names[0]: [round(s['ev_before'], 2), round(s['ev_after'], 2)],
                                   names[1]: [round(p['ev_before'], 2), round(p['ev_after'], 2)]})
        else:
            s = e['sw'][0]
            nm = names[e['track']]
            rec = dict(kind='single', tracks=[nm], final_pos=Ts(s['pos']), ambiguity=[Ts(s['lo']), Ts(s['hi'])],
                       ambiguity_ms=round((s['hi'] - s['lo']) / SR * 1000, 1), jump_s=Ts(s['jump']),
                       raw=[Ts(s['pos'] + s['o1']), Ts(s['pos'] + s['o2'])],
                       evidence_s={nm: [round(s['ev_before'], 2), round(s['ev_after'], 2)]})
        rec['type'] = 'cut' if rec['jump_s'] > 0 else 'backward_jump'
        evs = [v for pair in rec['evidence_s'].values() for v in pair]
        heard = [min(v) for v in rec['evidence_s'].values()]
        rec['confidence'] = 'high' if max(heard) >= 0.3 else ('medium' if max(evs) >= 0.3 else 'low')
        rec['ambiguity_capped'] = rec['ambiguity_ms'] >= 490
        ev_out.append(rec)
    ev_out.sort(key=lambda r: r['final_pos'])

    # ---------------- segments: constant (oL, oP) spans between refined boundaries / inserts
    cuts = {0: [], 1: []}
    for e, r in zip(events, [None] * len(events)):
        pass
    for e in events:
        if e['kind'] == 'joint':
            s, p = e['sw']
            ws, wp = s['hi'] - s['lo'], p['hi'] - p['lo']
            b = s if ws <= wp else p
            pos = b['pos']
            cuts[0].append((pos, s['o2']))
            cuts[1].append((pos, p['o2']))
        else:
            s = e['sw'][0]
            cuts[e['track']].append((s['pos'], s['o2']))

    def tsegs(ti, oX):
        out, start, cur = [], 0, int(oX[0])
        for pos, o2 in sorted(cuts[ti]):
            out.append((start, pos, cur))
            start, cur = pos, o2
        out.append((start, len(F), cur))
        return [x for x in out if x[1] > x[0]]

    TS = {0: tsegs(0, offL), 1: tsegs(1, offP)}
    edges = {0, len(F)}
    for ti in (0, 1):
        for a, b, _ in TS[ti]:
            edges.update((a, b))
    for a, b in ins:
        edges.update((a * HOP, min(b * HOP, len(F))))
    edges = sorted(edges)

    def off_at(ti, pos):
        for a, b, o in TS[ti]:
            if a <= pos < b:
                return o
        return TS[ti][-1][2]

    segs = []
    for a, b in zip(edges[:-1], edges[1:]):
        fa, fb = a // HOP, max(a // HOP + 1, b // HOP)
        if ins_frames[fa:fb].mean() > 0.5:
            if segs and segs[-1]['type'] == 'insert':
                segs[-1]['final_end'] = Ts(b)
            else:
                segs.append(dict(type='insert', final_start=Ts(a), final_end=Ts(b)))
            continue
        oL_, oP_ = off_at(0, a), off_at(1, a)
        if segs and segs[-1]['type'] == 'raw' and segs[-1]['_o'] == (oL_, oP_):
            segs[-1]['final_end'] = Ts(b); segs[-1]['_b'] = b
            continue
        segs.append(dict(type='raw', final_start=Ts(a), final_end=Ts(b), _a=a, _b=b, _o=(oL_, oP_)))
    for k, sg in enumerate(segs):
        sg['id'] = k
        sg['dur'] = round(sg['final_end'] - sg['final_start'], 4)
        if sg['type'] == 'insert':
            sg['confidence'] = 'high' if sg['dur'] > 3 else 'medium'
            continue
        a, b = sg.pop('_a'), sg.pop('_b')
        oL_, oP_ = sg.pop('_o')
        fa, fb = a // HOP, max(a // HOP + 1, b // HOP)
        cl, evl = track_conf(EL, fa, fb)
        cp, evp = track_conf(EP, fa, fb)
        rank = {'high': 3, 'medium': 2, 'low': 1, 'inferred': 0}
        best = max(rank[cl], rank[cp])
        sg.update(leon_src=[Ts(a + oL_), Ts(b + oL_)], pei_src=[Ts(a + oP_), Ts(b + oP_)],
                  offset_leon=Ts(oL_), offset_pei=Ts(oP_), pei_minus_leon_s=Ts(oP_ - oL_),
                  gain_leon=None if evl < 0.05 else round(float(np.median(GL[fa:fb][EL[fa:fb] > EVID_THR])), 3),
                  gain_pei=None if evp < 0.05 else round(float(np.median(GP[fa:fb][EP[fa:fb] > EVID_THR])), 3),
                  evidence_s={names[0]: round(evl, 2), names[1]: round(evp, 2)},
                  track_confidence={names[0]: cl, names[1]: cp},
                  confidence={3: 'high', 2: 'medium', 1: 'low', 0: 'low'}[best])

    raw_segs = [s for s in segs if s['type'] == 'raw']
    inserts = [s for s in segs if s['type'] == 'insert']

    # ---------------- probe inserts for raw material (e.g. a teaser cut from the episode)
    if not args.no_insert_probe:
        for sg in inserts:
            hits = []
            a, b = int(sg['final_start'] * SR), int(sg['final_end'] * SR)
            for t in range(a, b - 2 * SR, SR):
                i, c = S['mix'].search_global(F[t:t + 2 * SR])
                if c >= 0.4:
                    hits.append(dict(final=Ts(t), raw=Ts(i), ncc=round(c, 3)))
            sg['raw_probe_hits'] = hits
            sg['raw_probe_windows'] = max(0, (b - 2 * SR - a) // SR + 1)

    # ---------------- removed raw spans
    raw_len = len(L)

    def merge(iv):
        iv = sorted(iv)
        out = []
        for a, b in iv:
            if out and a <= out[-1][1] + 1e-3:
                out[-1][1] = max(out[-1][1], b)
            else:
                out.append([a, b])
        return out

    def complement(iv, total):
        res, cur = [], 0.0
        for a, b in iv:
            if a > cur + 1e-3:
                res.append([round(cur, 4), round(a, 4)])
            cur = max(cur, b)
        if total > cur + 1e-3:
            res.append([round(cur, 4), round(total, 4)])
        return res

    def intersect(A, B):
        i = j = 0
        out = []
        while i < len(A) and j < len(B):
            a, b = max(A[i][0], B[j][0]), min(A[i][1], B[j][1])
            if b > a + 1e-4:
                out.append([round(a, 4), round(b, 4)])
            if A[i][1] < B[j][1]:
                i += 1
            else:
                j += 1
        return out

    usedL = merge([tuple(s['leon_src']) for s in raw_segs])
    usedP = merge([tuple(s['pei_src']) for s in raw_segs])
    remL = complement(usedL, raw_len / SR)
    remP = complement(usedP, raw_len / SR)
    rem_both = intersect(remL, remP)

    # ---------------- inter-track offset (desync) timeline
    desync = []
    for s in raw_segs:
        d = s['pei_minus_leon_s']
        if desync and abs(desync[-1]['pei_minus_leon_s'] - d) < 1e-4:
            desync[-1]['final'][1] = s['final_end']
            desync[-1]['both_heard_s'] += min(s['evidence_s'][names[0]], s['evidence_s'][names[1]])
        else:
            desync.append(dict(final=[s['final_start'], s['final_end']], pei_minus_leon_s=d,
                               both_heard_s=min(s['evidence_s'][names[0]], s['evidence_s'][names[1]])))
    for d in desync:
        d['dur'] = round(d['final'][1] - d['final'][0], 3)
        d['both_heard_s'] = round(d['both_heard_s'], 2)

    # ---------------- muted spans: raw track speaks at its mapped position but is not heard in final
    muted = []
    for ti, (X, oX, EX) in enumerate(((L, offL, EL), (P, offP, EP))):
        xe = np.zeros(nfr)
        ch = np.flatnonzero(np.diff(oX)) + 1
        for a, b in zip(np.concatenate([[0], ch]), np.concatenate([ch, [nfr]])):
            seg = shifted(X, int(a) * HOP + int(oX[a]), (int(b) - int(a)) * HOP)
            xe[a:b] = frame_sums(seg, seg)
        xs = box(xe)
        noise = np.percentile(xs[xs > 0], 15) if (xs > 0).any() else 1e-12
        active = xs > noise * 100           # 20 dB above this track's noise floor
        mm = active & (box(EX) / (2 * SMOOTH_H + 1) < 0.03) & ~ins_frames
        for a, b, v in runs_of(mm.astype(np.int32)):
            if v and b - a >= 15:
                muted.append(dict(track=names[ti], final=[Tf(a), Tf(b)], dur=Tf(b - a),
                                  raw=[Ts(a * HOP + int(oX[a])), Ts(b * HOP + int(oX[a]))],
                                  raw_level_db_above_floor=round(float(10 * np.log10(np.median(xs[a:b]) / noise)), 1)))

    # ---------------- validation
    val = validate(F, L, P, raw_segs, fm, GL, GP, EL, EP, ins_frames)

    # ---------------- stats
    cuts_j = [r['jump_s'] for r in ev_out if r['kind'] == 'joint' and r['type'] == 'cut']
    cuts_s = [r for r in ev_out if r['kind'] == 'single' and r['type'] == 'cut']
    back = [r for r in ev_out if r['type'] == 'backward_jump']
    edges_h = [0, 0.2, 0.5, 1, 2, 5, 10, 30, 60, 1e9]
    hist = lambda v: np.histogram(v, edges_h)[0].tolist()
    stats = dict(
        raw_duration_s=Ts(raw_len), final_duration_s=Ts(len(F)),
        insert_total_s=round(sum(s['dur'] for s in inserts), 3), n_inserts=len(inserts),
        final_from_raw_s=round(sum(s['dur'] for s in raw_segs), 3),
        n_raw_segments=len(raw_segs),
        raw_used_s={names[0]: round(sum(b - a for a, b in usedL), 3), names[1]: round(sum(b - a for a, b in usedP), 3)},
        raw_removed_s={names[0]: round(sum(b - a for a, b in remL), 3), names[1]: round(sum(b - a for a, b in remP), 3),
                       'both_tracks': round(sum(b - a for a, b in rem_both), 3)},
        joint_cuts=dict(count=len(cuts_j), total_s=round(sum(cuts_j), 3),
                        under_1s=dict(count=int(sum(c < 1 for c in cuts_j)), total_s=round(sum(c for c in cuts_j if c < 1), 3)),
                        over_1s=dict(count=int(sum(c >= 1 for c in cuts_j)), total_s=round(sum(c for c in cuts_j if c >= 1), 3)),
                        hist_edges_s=edges_h[:-1], hist_counts=hist(cuts_j),
                        median_s=round(float(np.median(cuts_j)), 3) if cuts_j else None),
        single_track_cuts={nm: dict(count=sum(1 for r in cuts_s if r['tracks'] == [nm]),
                                    total_s=round(sum(r['jump_s'] for r in cuts_s if r['tracks'] == [nm]), 3),
                                    high_conf=sum(1 for r in cuts_s if r['tracks'] == [nm] and r['confidence'] == 'high'))
                           for nm in names},
        backward_jumps=dict(count=len(back), joint=sum(1 for r in back if r['kind'] == 'joint'),
                            single=sum(1 for r in back if r['kind'] == 'single'),
                            high_conf=sum(1 for r in back if r['confidence'] == 'high')),
        boundary_ambiguity_ms=dict(
            median=float(np.median([r['ambiguity_ms'] for r in ev_out])) if ev_out else None,
            p90=float(np.percentile([r['ambiguity_ms'] for r in ev_out], 90)) if ev_out else None,
            joint_high_conf_median=float(np.median([r['ambiguity_ms'] for r in ev_out if r['kind'] == 'joint' and r['confidence'] == 'high'] or [np.nan]))),
        joint_pos_disagreement_ms_median=float(np.median([r['pos_disagreement_ms'] for r in ev_out if r['kind'] == 'joint'] or [np.nan])),
        desync=dict(n_runs=len(desync), in_sync_s=round(sum(d['dur'] for d in desync if abs(d['pei_minus_leon_s']) < 1e-3), 1),
                    out_of_sync_s=round(sum(d['dur'] for d in desync if abs(d['pei_minus_leon_s']) >= 1e-3), 1)),
        muted_spans={nm: dict(count=sum(1 for m in muted if m['track'] == nm),
                              total_s=round(sum(m['dur'] for m in muted if m['track'] == nm), 2)) for nm in names},
        segment_confidence={c: sum(1 for s in raw_segs if s['confidence'] == c) for c in ('high', 'medium', 'low')},
        segment_confidence_s={c: round(sum(s['dur'] for s in raw_segs if s['confidence'] == c), 1) for c in ('high', 'medium', 'low')},
        median_gain={names[0]: float(np.median(GL[EL > 0.7])), names[1]: float(np.median(GP[EP > 0.7]))},
    )
    return dict(
        meta=dict(tool='lacuna spikes/s4_alignment/align.py', analysis_sr=SR, frame_s=HOP / SR,
                  lambda_joint=LAMBDA_JOINT, lambda_single=LAMBDA_SINGLE, evidence_threshold=EVID_THR,
                  inputs=dict(leon=os.path.basename(args.leon), pei=os.path.basename(args.pei), final=os.path.basename(args.final)),
                  conventions=('times in seconds. offset = raw_time - final_time. *_src = [raw_start, raw_end]. '
                               'jump_s = offset change at a boundary = raw seconds removed (>0) or re-used/backward (<0). '
                               'evidence_s = seconds in which that track is clearly heard (explained-energy > threshold). '
                               'track_confidence "inferred" = track silent there, offset carried by continuity.')),
        stats=stats, validation=val, segments=segs, edit_events=ev_out,
        removed_raw={'both_tracks': rem_both, names[0]: remL, names[1]: remP},
        inserts=inserts, desync_runs=desync, muted_track_spans=muted,
    )


def validate(F, L, P, raw_segs, fm, GL, GP, EL, EP, ins_frames):
    """Rebuild the final's raw-derived part from the map; correlate with the actual final."""
    R_seg = np.zeros(len(F), np.float32)
    R_loc = np.zeros(len(F), np.float32)
    R_mix = np.zeros(len(F), np.float32)      # ablation: both tracks forced to Leon's offset
    gl_all = float(np.median(GL[EL > 0.7])); gp_all = float(np.median(GP[EP > 0.7]))
    nfr = fm.nfr
    for s in raw_segs:
        a, b = int(round(s['final_start'] * SR)), int(round(s['final_end'] * SR))
        xl = shifted(L, a + int(round(s['offset_leon'] * SR)), b - a)
        xp = shifted(P, a + int(round(s['offset_pei'] * SR)), b - a)
        xp_m = shifted(P, a + int(round(s['offset_leon'] * SR)), b - a)
        gl = s['gain_leon'] if s['gain_leon'] is not None else gl_all
        gp = s['gain_pei'] if s['gain_pei'] is not None else gp_all
        R_seg[a:b] = gl * xl + gp * xp
        R_mix[a:b] = gl * xl + gp * xp_m
        fa = a // HOP
        idx = np.minimum(fa + np.arange(b - a) // HOP, nfr - 1)
        R_loc[a:b] = np.clip(GL[idx], 0, 20) * xl + np.clip(GP[idx], 0, 20) * xp
    keep = ~np.repeat(ins_frames, HOP)
    keep = np.concatenate([keep, np.zeros(len(F) - len(keep), bool)])
    f = F.astype(np.float64)
    W = SR
    nW = len(F) // W
    winkeep = keep[:nW * W].reshape(nW, W).mean(1) > 0.99
    fw = f[:nW * W].reshape(nW, W)
    fe = (fw ** 2).sum(1)
    out = {}
    for name, R in (('segment_gain', R_seg), ('local_gain', R_loc), ('ablation_tracks_forced_in_sync', R_mix)):
        r = R.astype(np.float64)
        num = np.sum(f[keep] * r[keep])
        den = np.sqrt(np.sum(f[keep] ** 2) * np.sum(r[keep] ** 2))
        res = f[keep] - r[keep]
        rw = r[:nW * W].reshape(nW, W)
        c = (fw * rw).sum(1) / (np.sqrt(fe * (rw ** 2).sum(1)) + 1e-12)
        sel = winkeep & (fe > np.percentile(fe[winkeep], 10))
        out[name] = dict(
            global_ncc=round(float(num / den), 4),
            residual_to_final_energy_db=round(float(10 * np.log10(np.sum(res ** 2) / np.sum(f[keep] ** 2))), 2),
            window_1s_ncc_pct={str(p): round(float(np.percentile(c[sel], p)), 3) for p in (1, 5, 10, 25, 50, 75, 90)},
            windows=int(sel.sum()), windows_below_0_8=int(np.sum(c[sel] < 0.8)), windows_below_0_5=int(np.sum(c[sel] < 0.5)),
            worst_windows=[[int(i), round(float(c[i]), 3)] for i in np.flatnonzero(sel)[np.argsort(c[sel])[:25]]],
        )
    # residual "bed" level in pauses: frames where both mapped raw tracks are quiet
    resid = f - R_loc
    rr = (resid[:nfr * HOP].reshape(nfr, HOP) ** 2).mean(1)
    rf = (f[:nfr * HOP].reshape(nfr, HOP) ** 2).mean(1)
    rl = (R_loc.astype(np.float64)[:nfr * HOP].reshape(nfr, HOP) ** 2).mean(1)
    quiet = (rl < np.percentile(rl[~ins_frames], 25)) & ~ins_frames
    db = lambda x: round(float(10 * np.log10(np.median(x) + 1e-15)), 1)
    out['pause_levels_db'] = dict(final=db(rf[quiet]), reconstruction=db(rl[quiet]), residual=db(rr[quiet]),
                                  speech_final=db(rf[(~quiet) & ~ins_frames]))
    # per-minute residual (in pauses) to locate music beds under speech
    per_min = []
    for m in range(0, nfr, 6000):
        q = quiet[m:m + 6000]
        if q.sum() > 100:
            per_min.append([round(m * HOP / SR), db(rf[m:m + 6000][q]), db(rr[m:m + 6000][q])])
    out['pause_levels_per_minute_db'] = per_min
    return out


if __name__ == '__main__':
    main()
