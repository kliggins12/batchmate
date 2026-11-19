#!/usr/bin/env python3
"""Batchmate rolling ticket generator - all games except All or Nothing
(see batchmate_rolling.py for AoN).

For each game, takes the last W draws, buckets numbers/digits by how often
they appear, builds candidate tickets from the rarest pieces, scores every
candidate against full history, and writes top 9 to rolling_<game>.txt.

Win rules match batchmate_build.py:
  pick3/daily4 : box match (sorted digits)
  cashfive     : 5/39, match >= 3
  twostep      : 4/35 + bonus, main>=3 or 2main+bonus
  lotto        : 6/54 (post 2006-04-26), match >= 4
"""

import csv, os, sys, itertools
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'data')
WINDOW = int(sys.argv[1]) if len(sys.argv) > 1 else 4
TOP = 9
SESS_ORDER = {'morning': 0, 'day': 1, 'evening': 2, 'night': 3}


def load(files, nfields, extra=None):
    rows = []
    for f in files + ([extra] if extra else []):
        path = os.path.join(DATA, f)
        if not os.path.exists(path):
            continue
        for r in csv.reader(open(path)):
            if len(r) < 4 + nfields:
                continue
            nums = tuple(int(x) for x in r[4:4 + nfields])
            sess = f.split('_')[1].split('.')[0] if '_' in f else 'x'
            rows.append(((int(r[3]), int(r[1]), int(r[2]), SESS_ORDER.get(sess, 9)),
                         nums))
    rows.sort(key=lambda x: x[0])
    return [n for _, n in rows]


def mask_of(nums):
    m = 0
    for v in nums:
        m |= 1 << (v - 1)
    return m


# ---------- digit games ----------

def digit_rolling(name, files):
    draws = load(files, 3 if 'pick3' in files[0] else 4)
    width = 3 if 'pick3' in files[0] else 4
    recent = draws[-WINDOW:]
    cnt = Counter()
    for d in recent:
        for v in set(d):
            cnt[v] += 1
    rare = sorted(v for v in range(10) if cnt[v] <= 2)
    while len(rare) < width:
        rare += [v for v in range(10) if v not in rare]
    rare = rare[:12]
    # candidate multisets: combinations_with_replacement of rare digits
    cands = set(itertools.combinations_with_replacement(sorted(rare), width))
    # history: box-match wins per candidate
    hist = [tuple(sorted(d)) for d in draws]
    scored = []
    for c in cands:
        wins = sum(1 for h in hist if h == c)
        # drought: draws since last win
        last = -1
        for i, h in enumerate(hist):
            if h == c:
                last = i
        drought = len(hist) - 1 - last if last >= 0 else len(hist)
        scored.append((wins, drought, c))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    out = os.path.join(HERE, f'rolling_{name.replace(" ", "_").lower()}.txt')
    with open(out, 'w') as f:
        f.write(f'Batchmate rolling {name} - last {WINDOW} draws\n{TOP} tickets (box match; any digit order wins same)\n\n')
        for w, dr, c in scored[:TOP]:
            f.write(''.join(map(str, c)) + f'   # box wins={w} drought={dr}\n')
    print(f'[{name}] {len(cands)} cands, top: ' +
          ', '.join(''.join(map(str, c)) for _, _, c in scored[:TOP]))


# ---------- combo games ----------

def combo_rolling(name, draws, k, nmax, winfun, bonus=False):
    recent = draws[-WINDOW:]
    cnt = Counter()
    for d in recent:
        for v in set(d[:k] if bonus else d):
            cnt[v] += 1
    core = sorted(v for v in range(1, nmax + 1) if cnt[v] <= 2)
    fillers = sorted(v for v in range(1, nmax + 1) if cnt[v] >= 3)
    while len(core) < k and fillers:
        core.append(fillers.pop(0))
    core = sorted(core)
    cap = {5: 12, 4: 12, 6: 12}[k]
    core = core[:cap]
    cands = list(itertools.combinations(core, k))
    # swap variants with 3x fillers (small games only)
    sw = set(cands)
    if k <= 4:
        for c in cands[:200]:
            for old in c:
                for f in fillers[:6]:
                    if f not in c:
                        sw.add(tuple(sorted((set(c) - {old}) | {f})))
    cands = list(sw)
    dmasks = [mask_of(d[:k] if bonus else d) for d in draws]
    bnums = [d[k] if bonus else 0 for d in draws]
    scored = []
    for c in cands:
        cm = mask_of(c)
        wins = 0
        for i, dm in enumerate(dmasks):
            inter = (cm & dm).bit_count()
            ok = inter >= 3 if bonus else winfun(inter, bnums[i], c)
            if ok:
                wins += 1
        scored.append((wins, c))
    scored.sort(key=lambda x: -x[0])
    top_main = scored[:TOP * 4]

    tickets = []
    if bonus:
        # evaluate top mains x all bonuses under full rule
        for w, c in top_main:
            cm = mask_of(c)
            for b in range(1, nmax + 1):
                wins = 0
                for i, dm in enumerate(dmasks):
                    inter = (cm & dm).bit_count()
                    if inter >= 3 or (inter == 2 and bnums[i] == b):
                        wins += 1
                tickets.append((wins, c, b))
        tickets.sort(key=lambda x: -x[0])
        lines = [f'{",".join(map(str,c))} + {b}   # wins={w}' for w, c, b in tickets[:TOP]]
    else:
        lines = [f'{",".join(map(str,c))}   # wins={w}' for w, c in top_main[:TOP]]
    out = os.path.join(HERE, f'rolling_{name.replace(" ", "_").lower()}.txt')
    with open(out, 'w') as f:
        f.write(f'Batchmate rolling {name} - last {WINDOW} draws\n{TOP} tickets\n\n' + '\n'.join(lines) + '\n')
    print(f'[{name}] {len(cands)} cands')
    for l in lines:
        print('   ', l)


def main():
    p3 = ['pick3morning.csv', 'pick3day.csv', 'pick3evening.csv', 'pick3night.csv']
    d4 = ['daily4morning.csv', 'daily4day.csv', 'daily4evening.csv', 'daily4night.csv']
    for f in p3:
        sess = f.replace('pick3', '').replace('.csv', '').title()
        digit_rolling(f'Pick 3 {sess}', [f])
    for f in d4:
        sess = f.replace('daily4', '').replace('.csv', '').title()
        digit_rolling(f'Daily 4 {sess}', [f])

    cf = load(['cashfive.csv'], 5)
    combo_rolling('Cash Five', cf, 5, 39, lambda i, b, c: i >= 3)

    ts = load(['texastwostep.csv'], 5)
    combo_rolling('Texas Two Step', ts, 4, 35, None, bonus=True)

    # lotto: post-2006 only
    lt = []
    for r in csv.reader(open(os.path.join(DATA, 'lottotexas.csv'))):
        if len(r) < 10:
            continue
        y, m, d = int(r[3]), int(r[1]), int(r[2])
        if y > 2006 or (y == 2006 and (m > 4 or (m == 4 and d >= 26))):
            lt.append(tuple(int(x) for x in r[4:10]))
    combo_rolling('Lotto Texas', lt, 6, 54, lambda i, b, c: i >= 4)


if __name__ == '__main__':
    main()
