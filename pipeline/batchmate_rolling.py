#!/usr/bin/env python3
"""Batchmate rolling ticket generator (All or Nothing).

Takes the last W draws across the four AoN sessions, counts how often each
number 1-24 appears, extracts the 'piece' pools:

  unique : appears in exactly 1 of the W draws
  absent : appears in 0 draws
  twice  : appears in 2 draws
  three  : appears in 3 draws (used as swap fillers)

Builds tight 12-number canonical candidates (must contain 1) from those
pieces plus swap variants, scores every candidate against the full draw
history (e<=2 prize hits), and writes the top 9 to aon_rolling_tickets.txt.

Rerun after new draws are added to data/aon_*.csv (or data/aon_extra.csv).
"""

import csv, re, sys, os
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'data')
WINDOW = int(sys.argv[1]) if len(sys.argv) > 1 else 4
TOP = 9
OUT = os.path.join(HERE, 'aon_rolling_tickets.txt')
ALL = set(range(1, 25))
SESS_ORDER = {'morning': 0, 'day': 1, 'evening': 2, 'night': 3}


def load_draws():
    rows = []
    for f in ['aon_morning.csv', 'aon_day.csv', 'aon_evening.csv', 'aon_night.csv', 'aon_extra.csv']:
        path = os.path.join(DATA, f)
        if not os.path.exists(path):
            continue
        for r in csv.reader(open(path)):
            if len(r) < 16:
                continue
            nums = tuple(sorted(int(x) for x in r[4:16]))
            sess = f.split('_')[1].split('.')[0]
            rows.append(((int(r[3]), int(r[1]), int(r[2]), SESS_ORDER.get(sess, 9)),
                         f"{int(r[1])}/{int(r[2])}/{int(r[3])} {sess}", nums))
    rows.sort(key=lambda x: x[0])
    return rows


def canon(nums):
    return nums if nums[0] == 1 else tuple(sorted(ALL - set(nums)))


def history_masks():
    masks = []
    for _, _, nums in load_draws():
        c = canon(nums)
        masks.append(sum(1 << (v - 1) for v in c))
    return masks


def score(cand, masks):
    tm = sum(1 << (v - 1) for v in cand)
    e1 = e2 = jack = 0
    for dm in masks:
        k = (tm & dm).bit_count()
        e = 12 - max(k, 12 - k)
        if e == 0:
            jack += 1
        elif e == 1:
            e1 += 1
        elif e == 2:
            e2 += 1
    return e1, e2, jack


def main():
    rows = load_draws()
    recent = rows[-WINDOW:]
    print(f'window = last {WINDOW} draws:')
    for _, ds, nums in recent:
        print('  ', ds, ','.join(map(str, nums)))

    cnt = Counter()
    for _, _, nums in recent:
        for v in nums:
            cnt[v] += 1

    buckets = {i: sorted(v for v in range(1, 25) if cnt[v] == i) for i in range(5)}
    for i in range(5):
        print(f'  seen {i}x: {buckets[i]}')

    core = buckets[1] + buckets[0] + buckets[2]
    three = buckets[3] + buckets[4]
    # ensure pool big enough for 12-number tickets containing 1
    while len(core) < 12 and three:
        core.append(three.pop(0))
    core = sorted(core)

    # candidate set: all 12-subsets of core containing 1 (cap core at 16)
    core = core[:16]
    import itertools
    cands = set()
    if 1 in core:
        others = [v for v in core if v != 1]
        for combo in itertools.combinations(others, 11):
            cands.add(tuple(sorted((1,) + combo)))
    else:
        for combo in itertools.combinations(core, 12):
            cands.add(combo)
    # swap variants: replace one non-1 member with a 3x-seen filler
    fillers = three[:8]
    base = list(cands)
    for c in base:
        for old in c:
            if old == 1:
                continue
            for f in fillers:
                if f in c:
                    continue
                cands.add(tuple(sorted((set(c) - {old}) | {f})))
    cands = list(cands)
    print(f'{len(cands)} candidates')

    masks = history_masks()
    print(f'{len(masks)} historical draws')

    scored = []
    for c in cands:
        e1, e2, jack = score(c, masks)
        scored.append((e1, e2, -jack, c))
    scored.sort(key=lambda x: (-x[0], -x[1], x[2]))

    top = scored[:TOP]
    with open(OUT, 'w') as f:
        f.write(f'Batchmate rolling set - last {WINDOW} AoN draws\n')
        f.write(f'{TOP} tickets x $2 = ${TOP*2}\n\n')
        for e1, e2, nj, c in top:
            odds = sum(v % 2 for v in c)
            f.write(','.join(map(str, c)) +
                    f'   # e1={e1} e2={e2} jack={-nj} sum={sum(c)} {odds}o/{12-odds}e\n')
    print('\nTOP', TOP)
    for e1, e2, nj, c in top:
        odds = sum(v % 2 for v in c)
        print(f'  e1={e1:2d} e2={e2:3d} jack={-nj} sum={sum(c):3d} {odds}o/{12-odds}e  {",".join(map(str,c))}')
    print(f'\nwrote {OUT}')


if __name__ == '__main__':
    main()
