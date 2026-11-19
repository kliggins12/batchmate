#!/usr/bin/env python3
"""Batchmate Align - rule-based aligned-count ticket generator (AoN).

For each stream (interleaved + 4 sessions) and each window tier (W=4, W=12):
  count[v] = # of window draws containing v (per-draw presence, not multiplicity)

Decision rules (first match wins):
  R1 ABSENT-ANCHOR : if absent numbers exist -> keep ALL absent, fill by hot freq
  R2 BAND-KEEP     : else keep the count-level group sized 4..8 (closest to 6),
                     fill hot; if tie prefer level nearer the window median
  R3 HOT-CORE      : else (no suitable band) keep top-6 hottest, fill warm
  Signature fix    : if result deviates >2 from 6/6 odds, swap extremes to fix
  Canon fix        : if ticket lacks 1, replace lowest-count member with 1
                    (unless 1 is absent->already kept)
Output: deduped ticket list with rule + stats, written to aon_align_rules.txt
"""
import csv, os, sys
import numpy as np
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'data')
SESS = {'morning': 0, 'day': 1, 'evening': 2, 'night': 3}
FULL = (1 << 24) - 1
ALL = set(range(1, 25))
ODDS = list(range(1, 24, 2))
EVENS = list(range(2, 24, 2))


def load():
    rows = []
    for f in ['aon_morning.csv', 'aon_day.csv', 'aon_evening.csv', 'aon_night.csv']:
        sess = f.split('_')[1].split('.')[0]
        for r in csv.reader(open(os.path.join(DATA, f))):
            if len(r) < 16:
                continue
            nums = tuple(sorted(int(x) for x in r[4:16]))
            rows.append(((int(r[3]), int(r[1]), int(r[2]), SESS[sess], sess), nums))
    rows.sort(key=lambda x: x[0])
    return rows


def canon(nums):
    s = set(nums)
    return s if 1 in s else ALL - s


def build_ticket(cnt, W):
    """Return (ticket_set, rule_tag)."""
    absent = [v for v in range(1, 25) if cnt[v] == 0]
    # R1: absent anchor
    if absent:
        keep = set(absent)
        rest = sorted((v for v in range(1, 25) if v not in keep),
                      key=lambda v: (-cnt[v], v))
        t = set(sorted(keep | set(rest[:12 - len(keep)])))
        return t, f'R1 absent({len(absent)})'

    # R2: band keep - count level with group size closest to 6 within 4..8
    levels = {}
    for v in range(1, 25):
        levels.setdefault(cnt[v], []).append(v)
    cands = [(L, vs) for L, vs in levels.items() if 4 <= len(vs) <= 8]
    if cands:
        med = sorted(cnt.values())[12]
        L, vs = min(cands, key=lambda x: (abs(len(x[1]) - 6), abs(x[0] - med)))
        keep = set(vs)
        rest = sorted((v for v in range(1, 25) if v not in keep),
                      key=lambda v: (-cnt[v], v))
        t = set(sorted(keep | set(rest[:12 - len(keep)])))
        return t, f'R2 band(L={L},n={len(vs)})'

    # R3: hot core - top 6 hottest + warm fill
    hot = sorted(range(1, 25), key=lambda v: (-cnt[v], v))[:6]
    rest = sorted((v for v in range(1, 25) if v not in hot),
                  key=lambda v: (-cnt[v], v))
    t = set(hot) | set(rest[:6])
    return t, 'R3 hotcore'


def signature_fix(t, cnt):
    """If odd count deviates from 6 by >2, swap extreme-count members."""
    o = sum(1 for v in t if v % 2 == 1)
    if abs(o - 6) <= 2:
        return t, ''
    need_more_odds = o < 6
    pool_out = sorted(t, key=lambda v: (cnt[v], v))          # coldest out
    pool_in = sorted((v for v in range(1, 25) if v not in t),
                     key=lambda v: (-cnt[v], v))             # hottest in
    t = set(t)
    while (sum(1 for v in t if v % 2 == 1) < 6) if need_more_odds else \
          (sum(1 for v in t if v % 2 == 1) > 6):
        swapped = False
        for vout in pool_out:
            want_par = 1 if need_more_odds else 0
            for vin in pool_in:
                if vin % 2 == want_par and vin not in t:
                    t.discard(vout); t.add(vin)
                    pool_out.remove(vout); pool_in.remove(vin)
                    swapped = True
                    break
            if swapped:
                break
        if not swapped:
            break
    return t, f'sigfix->{sum(1 for v in t if v % 2 == 1)}o'


def canon_fix(t, cnt):
    if 1 in t:
        return t, ''
    # replace coldest non-1 member with 1 (1 is canonical anchor)
    vout = min(t, key=lambda v: (cnt[v], -v))
    t = set(t); t.discard(vout); t.add(1)
    return t, f'canonfix(-{vout}+1)'


def auto_peak(rows, draws, meta, dm, max_w=16):
    """Per stream: scan W from max_w down to 2, keep best (e2,e1) rule ticket."""
    streams = {'interleaved': list(range(len(draws)))}
    for s in ['morning', 'day', 'evening', 'night']:
        streams[s] = [i for i, m in enumerate(meta) if m[4] == s]

    def score(t):
        tm = sum(1 << (v - 1) for v in t)
        k = np.bitwise_count(dm & np.uint32(tm))
        e = 12 - np.maximum(k, 12 - k)
        return int((e == 1).sum()), int((e <= 2).sum()), int((e == 0).sum())

    out = []
    seen = set()
    for s, idxs in streams.items():
        n = len(idxs)
        best = None
        # start large, tighten smaller
        for W in range(min(max_w, n), 1, -1):
            cnt = Counter()
            for i in idxs[-W:]:
                for v in set(draws[i]):
                    cnt[v] += 1
            t, rule = build_ticket(cnt, W)
            t, _ = signature_fix(t, cnt)
            t, _ = canon_fix(t, cnt)
            tt = tuple(sorted(t))
            e1, e2, j = score(tt)
            if best is None or (e2, e1) > (best[1], best[2]):
                best = (W, e2, e1, j, rule, tt)
        W, e2, e1, j, rule, tt = best
        if tt in seen:
            continue
        seen.add(tt)
        sig = f"{sum(1 for v in tt if v % 2 == 1)}o/{12 - sum(1 for v in tt if v % 2 == 1)}e"
        out.append((e1, e2, j, s, W, rule, sig, tt))
    out.sort(key=lambda x: (-x[0], -x[1]))
    return out


def main():
    rows = load()
    draws = [n for _, n in rows]
    meta = [k for k, _ in rows]
    cd = [d if d[0] == 1 else tuple(sorted(ALL - set(d))) for d in draws]
    dm = np.array([sum(1 << (v - 1) for v in c) for c in cd], np.uint32)

    if '--auto' in sys.argv:
        out = auto_peak(rows, draws, meta, dm,
                        max_w=int(sys.argv[sys.argv.index('--max-w') + 1]) if '--max-w' in sys.argv else 16)
        with open(os.path.join(HERE, 'aon_align_auto.txt'), 'w') as f:
            f.write('Batchmate Align AUTO - peak window per stream (W scanned large->small)\n\n')
            for e1, e2, j, s, W, rule, sig, t in out:
                f.write(f'[{s} W={W}] {rule} sig={sig}\n')
                f.write(f'  e1={e1} e2={e2} jack={j}\n')
                f.write(f'  {",".join(map(str, t))}\n\n')
        for e1, e2, j, s, W, rule, sig, t in out:
            print(f'[{s:11s} W={W:2d}] {rule:24s} sig={sig} e1={e1} e2={e2} | {",".join(map(str,t))}')
        print(f'\n{len(out)} tickets -> aon_align_auto.txt')
        return

    def score(t):
        tm = sum(1 << (v - 1) for v in t)
        k = np.bitwise_count(dm & np.uint32(tm))
        e = 12 - np.maximum(k, 12 - k)
        return int((e == 1).sum()), int((e <= 2).sum()), int((e == 0).sum())

    streams = {'interleaved': list(range(len(draws)))}
    for s in ['morning', 'day', 'evening', 'night']:
        streams[s] = [i for i, m in enumerate(meta) if m[4] == s]

    out = []
    seen = set()
    for s, idxs in streams.items():
        for W in (4, 12):
            w = idxs[-W:]
            if len(w) < W:
                continue
            cnt = Counter()
            for i in w:
                for v in set(draws[i]):
                    cnt[v] += 1
            t, rule = build_ticket(cnt, W)
            fixes = []
            t, f1 = signature_fix(t, cnt)
            if f1: fixes.append(f1)
            t, f2 = canon_fix(t, cnt)
            if f2: fixes.append(f2)
            tt = tuple(sorted(t))
            if tt in seen:
                continue
            seen.add(tt)
            e1, e2, j = score(t)
            sig = f"{sum(1 for v in t if v%2==1)}o/{12-sum(1 for v in t if v%2==1)}e"
            out.append((e1, e2, j, s, W, rule + ('+' + '+'.join(fixes) if fixes else ''), sig, tt))

    out.sort(key=lambda x: (-x[0], -x[1]))
    with open(os.path.join(HERE, 'aon_align_rules.txt'), 'w') as f:
        f.write('Batchmate Align - rule-based tickets\n')
        f.write('streams x W{4,12}; rules R1 absent-anchor / R2 band-keep / R3 hotcore + sigfix + canonfix\n\n')
        for e1, e2, j, s, W, rule, sig, t in out:
            f.write(f'[{s} W={W}] {rule} sig={sig}\n')
            f.write(f'  e1={e1} e2={e2} jack={j}\n')
            f.write(f'  {",".join(map(str, t))}\n\n')
    for e1, e2, j, s, W, rule, sig, t in out:
        print(f'[{s:11s} W={W:2d}] {rule:28s} sig={sig} e1={e1} e2={e2} | {",".join(map(str,t))}')
    print(f'\n{len(out)} unique tickets -> aon_align_rules.txt')


if __name__ == '__main__':
    main()
