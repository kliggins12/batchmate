#!/usr/bin/env python3
"""Batchmate rolling + best-of for Powerball and Mega Millions.

Data: data/powerball.csv, data/megamillions.csv (Louisiana Lottery export).
Eras: PB current matrix 5/69 + PB 1-26 (since 2015-10-07);
      MM 5/70 era (since 2020-03-24; bonus pool 25->24 in 2026, noted).

Win tiers counted per ticket (mains c, bonus b):
  J  = 5 mains + bonus          (jackpot)
  W5 = 5 mains                  ($1M tier)
  W4B= 4 mains + bonus
  W4 = 4 mains
  W3B= 3 mains + bonus
  prize = any of the above (match>=3 with bonus rules approximated:
          we count match>=4 mains always, match==3 only with bonus)

Rolling: last WINDOW draws -> rare pieces (seen <=2) -> C(core,5) mains
-> top mains x all bonuses -> score vs full era history -> top 9.
"""
import csv, os, re, sys, itertools
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'data')
WINDOW = int(sys.argv[1]) if len(sys.argv) > 1 else 4
TOP = 9


def load(fname, bonus_min_date):
    rows = []
    for r in csv.reader(open(os.path.join(DATA, fname))):
        if len(r) < 7 or not re.match(r'^\d{4}-\d{2}-\d{2}$', r[0]):
            continue
        if r[0] < bonus_min_date:
            continue
        nums = tuple(int(x) for x in r[1:7])
        rows.append((r[0], nums))
    rows.sort()
    return rows


def mask_of(nums):
    m = 0
    for v in nums:
        m |= 1 << (v - 1)
    return m


def run(name, fname, cutoff, nmax, bmax):
    rows = load(fname, cutoff)
    draws = [n for _, n in rows]
    dates = [d for d, _ in rows]
    dm = [mask_of(d[:5]) for d in draws]
    db = [d[5] for d in draws]

    recent = draws[-WINDOW:]
    cnt = Counter()
    for d in recent:
        for v in set(d[:5]):
            cnt[v] += 1
    rare = sorted(v for v in range(1, nmax + 1) if cnt[v] <= 2)
    fillers = [v for v in range(1, nmax + 1) if v not in rare]
    fillers.sort(key=lambda v: (cnt[v], v))
    while len(rare) < 5 and fillers:
        rare.append(fillers.pop(0))
    core = sorted(rare)[:14]

    # stage 1: score mains on match>=4 count
    mains_scored = []
    for c in itertools.combinations(core, 5):
        cm = mask_of(c)
        w4 = sum(1 for i, m in enumerate(dm) if (cm & m).bit_count() >= 4)
        j5 = sum(1 for i, m in enumerate(dm) if (cm & m).bit_count() == 5)
        mains_scored.append((w4 + j5 * 3, j5, w4, c))
    mains_scored.sort(key=lambda x: (-x[0], -x[1]))
    top_mains = mains_scored[:60]

    # stage 2: mains x bonus, full prize count
    tickets = []
    for _, j5, w4, c in top_mains:
        cm = mask_of(c)
        for b in range(1, bmax + 1):
            J = W5 = W4B = W4 = W3B = 0
            for i, m in enumerate(dm):
                inter = (cm & m).bit_count()
                has_b = db[i] == b
                if inter == 5 and has_b: J += 1
                elif inter == 5: W5 += 1
                elif inter == 4 and has_b: W4B += 1
                elif inter == 4: W4 += 1
                elif inter == 3 and has_b: W3B += 1
            prize = J + W5 + W4B + W4 + W3B
            tickets.append((prize, J, W5, W4B, W4, W3B, c, b))
    tickets.sort(key=lambda x: (-x[0], -x[1], -x[2]))

    out = os.path.join(HERE, f'rolling_{name.lower().replace(" ", "_")}.txt')
    with open(out, 'w') as f:
        f.write(f'Batchmate rolling {name} - last {WINDOW} draws (era since {cutoff})\n')
        f.write(f'{TOP} tickets | prize=J+W5+W4B+W4+W3B\n\n')
        for p, J, W5, W4B, W4, W3B, c, b in tickets[:TOP]:
            f.write(f'{",".join(map(str, c))} + {b}   # prize={p} J={J} W5={W5} W4B={W4B} W4={W4} W3B={W3B}\n')
    print(f'[{name}] {len(draws)} draws in era, {len(core)} core nums, {len(tickets)} tickets scored')
    for p, J, W5, W4B, W4, W3B, c, b in tickets[:TOP]:
        print(f'   {",".join(map(str,c))} + {b}  prize={p} J={J} W5={W5} W4B={W4B} W4={W4} W3B={W3B}')


def main():
    run('Powerball', 'powerball.csv', '2015-10-07', 69, 26)
    run('Mega Millions', 'megamillions.csv', '2020-03-24', 70, 25)


if __name__ == '__main__':
    main()
