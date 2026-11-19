#!/usr/bin/env python3
"""Batchmate data builder.

For each Texas Lottery game, tracks every playable ticket's win streaks
across official draw history and emits batchmate_data.json for the web app.

Win rules (historical prize proxies):
  pick3/daily4 : box match (sorted digits equal, any order)
  cashfive     : 5/39, win = match >= 3
  twostep      : 4/35 + bonus 1/35, win = main match >= 3 OR (2 main + bonus)
  lottotexas   : 6/54 (draws from 2006-04-26), win = match >= 5
  aon          : canonical half-library leftover pool, win = e <= 2

Streak definition: consecutive draws (in chronological order) where the
ticket met the win rule. best = longest such streak; we record its end draw.
"""

import csv, json, os, sys, time
from itertools import combinations
from collections import defaultdict

import numpy as np

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'batchmate_data.json')

TOP_N = 300


def parse_date(r):
    return (int(r[3]), int(r[1]), int(r[2]))  # y,m,d -> sortable


def date_str(r):
    return f"{int(r[1])}/{int(r[2])}/{int(r[3])}"


def load_draws(files, num_fields):
    """Return sorted list of (sortkey, datestr, tuple-of-ints)."""
    draws = []
    for f in files:
        path = os.path.join(DATA, f)
        if not os.path.exists(path):
            continue
        for r in csv.reader(open(path)):
            if len(r) < 4 + num_fields:
                continue
            try:
                nums = tuple(int(x) for x in r[4:4 + num_fields])
            except ValueError:
                continue
            draws.append((parse_date(r), date_str(r), nums))
    draws.sort(key=lambda x: x[0])
    return [(d, n) for _, d, n in draws], [d for _, d, _ in draws]


# ---------- generic streak engine ----------

def run_streaks(n_tickets, draw_winners, dates):
    """draw_winners: list of np arrays of ticket indices winning each draw."""
    streak = np.zeros(n_tickets, np.int32)
    best = np.zeros(n_tickets, np.int32)
    last = np.full(n_tickets, -10**9, np.int32)
    total = np.zeros(n_tickets, np.int32)
    best_end = np.full(n_tickets, -1, np.int32)
    for di, W in enumerate(draw_winners):
        # A current streak must be zero for every ticket that misses this draw.
        # Preserve the previous values for winners before clearing the array.
        previous = streak[W].copy()
        streak.fill(0)
        if len(W) == 0:
            continue
        ns = np.where(last[W] == di - 1, previous + 1, 1).astype(np.int32)
        streak[W] = ns
        last[W] = di
        total[W] += 1
        imp = ns > best[W]
        if imp.any():
            w = W[imp]
            best[w] = ns[imp]
            best_end[w] = di
    return streak, best, total, best_end


def top_records(game, ticket_strs, streak, best, total, best_end, last_win, dates):
    n = len(ticket_strs)
    nd = len(dates)
    order = np.lexsort((-best_end, -best, -total))[:TOP_N]
    recs = []
    for i in order:
        i = int(i)
        be = int(best_end[i])
        lw = int(last_win[i])
        recs.append({
            'ticket': ticket_strs[i],
            'total_wins': int(total[i]),
            'best_streak': int(best[i]),
            'streak_start': dates[be - int(best[i]) + 1] if be >= 0 and int(best[i]) > 0 else None,
            'streak_end': dates[be] if be >= 0 else None,
            'last_win': dates[lw] if lw >= 0 else None,
            'drought': (nd - 1 - lw) if lw >= 0 else nd,
            'current_streak': int(streak[i]),
        })
    return recs


# ---------- digit games (box match) ----------

def digit_game(name, files, width):
    draws, dates = load_draws(files, width)
    n = 10 ** width
    # boxkey -> list of ticket ids (all permutations of the multiset)
    box2ids = defaultdict(list)
    for tid in range(n):
        digs = tuple(int(c) for c in f"{tid:0{width}d}")
        box2ids[tuple(sorted(digs))].append(tid)
    winners = []
    for _, nums in draws:
        key = tuple(sorted(nums))
        winners.append(np.array(box2ids.get(key, []), dtype=np.int64))
    streak, best, total, best_end = run_streaks(n, winners, dates)
    # last win date: recompute cheaply = last draw index each ticket won
    last_win = np.full(n, -1, np.int32)
    for di, W in enumerate(winners):
        last_win[W] = di
    tix = [f"{i:0{width}d}" for i in range(n)]
    return {
        'name': name, 'type': 'digits', 'width': width,
        'n_tickets': n, 'n_draws': len(draws),
        'dates': dates, 'win_rule': 'box match',
        'top': top_records(name, tix, streak, best, total, best_end, last_win, dates),
    }


# ---------- number-combo games ----------

def combo_masks(combos):
    """combos: iterable of sorted tuples -> uint64 mask array."""
    arr = np.zeros(len(combos), np.uint64)
    for i, c in enumerate(combos):
        m = 0
        for v in c:
            m |= 1 << (v - 1)
        arr[i] = m
    return arr


def gen_combos(n, k):
    return list(combinations(range(1, n + 1), k))


def cashfive():
    draws, dates = load_draws(['cashfive.csv'], 5)
    combos = gen_combos(39, 5)
    masks = combo_masks(combos)
    winners = []
    for _, nums in draws:
        dm = 0
        for v in nums:
            dm |= 1 << (v - 1)
        m = np.bitwise_count(masks & np.uint64(dm))
        winners.append(np.nonzero(m >= 3)[0].astype(np.int64))
    streak, best, total, best_end = run_streaks(len(combos), winners, dates)
    last_win = np.full(len(combos), -1, np.int32)
    for di, W in enumerate(winners):
        last_win[W] = di
    tix = [','.join(map(str, c)) for c in combos]
    return {
        'name': 'Cash Five', 'type': 'numbers', 'pick': '5/39',
        'n_tickets': len(combos), 'n_draws': len(draws),
        'dates': dates, 'win_rule': 'match >= 3',
        'top': top_records('Cash Five', tix, streak, best, total, best_end, last_win, dates),
    }


def twostep():
    draws, dates = load_draws(['texastwostep.csv'], 5)
    main_combos = gen_combos(35, 4)
    masks = combo_masks(main_combos)  # 52,360
    n_tix = len(main_combos) * 35
    winners = []
    all_b = np.arange(35, dtype=np.int64)
    for _, nums in draws:
        dm = 0
        for v in nums[:4]:
            dm |= 1 << (v - 1)
        m = np.bitwise_count(masks & np.uint64(dm))
        idx3 = np.nonzero(m >= 3)[0]
        W = (idx3[:, None] * 35 + all_b[None, :]).ravel()
        idx2 = np.nonzero(m == 2)[0]
        if len(idx2):
            W = np.concatenate([W, idx2 * 35 + (nums[4] - 1)])
        winners.append(W.astype(np.int64))
    streak, best, total, best_end = run_streaks(n_tix, winners, dates)
    last_win = np.full(n_tix, -1, np.int32)
    for di, W in enumerate(winners):
        last_win[W] = di
    tix = []
    for c in main_combos:
        cs = ','.join(map(str, c))
        for b in range(1, 36):
            tix.append(f"{cs} + {b}")
    return {
        'name': 'Texas Two Step', 'type': 'numbers', 'pick': '4/35 + 1/35',
        'n_tickets': n_tix, 'n_draws': len(draws),
        'dates': dates, 'win_rule': 'main>=3 or 2main+bonus',
        'top': top_records('Texas Two Step', tix, streak, best, total, best_end, last_win, dates),
    }


# ---------- Lotto Texas (post-2006 6/54) ----------

# lex rank for combinations of k=6 from 1..54 in itertools.combinations order
def build_rank_tables(n=54, k=6):
    # comb[a][b] = C(a,b)
    comb = np.zeros((n + 2, k + 1), np.int64)
    for a in range(n + 2):
        comb[a, 0] = 1
        for b in range(1, min(a, k) + 1):
            comb[a, b] = comb[a - 1, b - 1] + comb[a - 1, b]
    # P[i][x] = sum_{y=1}^{x} C(n - y, k - 1 - i)  for i in 0..k-1
    P = np.zeros((k, n + 2), np.int64)
    for i in range(k):
        kk = k - 1 - i
        for x in range(1, n + 1):
            P[i, x] = P[i, x - 1] + (comb[n - x, kk] if n - x >= kk else 0)
    return comb, P


def lex_rank(combo, comb, P, n=54, k=6):
    """combo sorted 1..n tuple -> rank in itertools.combinations order."""
    rank = 0
    prev = 0
    for i, v in enumerate(combo):
        # elements prev+1 .. v-1 skipped at position i
        rank += P[i, v - 1] - P[i, prev]
        prev = v
    return rank


def lotto():
    t0 = time.time()
    # 6/54 era only (post 2006-04-26)
    raw = []
    for r in csv.reader(open(os.path.join(DATA, 'lottotexas.csv'))):
        if len(r) < 10:
            continue
        y, m, d = int(r[3]), int(r[1]), int(r[2])
        if y > 2006 or (y == 2006 and (m > 4 or (m == 4 and d >= 26))):
            nums = tuple(int(x) for x in r[4:10])
            raw.append(((y, m, d), f"{m}/{d}/{y}", nums))
    raw.sort(key=lambda x: x[0])
    dates = [x[1] for x in raw]
    draws = [x[2] for x in raw]

    N = 25_827_165
    masks = np.load(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 '_archive', 'lotto_masks.npy'), mmap_mode='r')
    order = np.argsort(masks)
    sorted_masks = np.asarray(masks)[order]
    del masks
    print(f'  lotto masks sorted in {time.time()-t0:.0f}s', flush=True)

    # bit value per number 1..54
    bit = np.uint64(1)
    winners = []
    for nums in draws:
        s = sorted(nums)
        elems = s
        undrawn = [v for v in range(1, 55) if v not in set(s)]
        # 6-match + 5-match winners (289)
        W = [sum(1 << (v - 1) for v in s)]
        for i in range(6):
            base = sum(1 << (v - 1) for j, v in enumerate(s) if j != i)
            for v in undrawn:
                W.append(base | (1 << (v - 1)))
        # 4-match winners: 4-subset of drawn x 2-subset of undrawn
        for sub in combinations(range(6), 4):
            m4 = sum(1 << (elems[j] - 1) for j in sub)
            for a_i in range(len(undrawn)):
                for b_i in range(a_i + 1, len(undrawn)):
                    W.append(m4 | (1 << (undrawn[a_i] - 1)) | (1 << (undrawn[b_i] - 1)))
        wm = np.array(W, np.uint64)
        pos = np.searchsorted(sorted_masks, wm)
        winners.append(order[pos].astype(np.int64))
    print(f'  lotto winners done in {time.time()-t0:.0f}s', flush=True)

    streak = np.zeros(N, np.int16)
    best = np.zeros(N, np.int16)
    last = np.full(N, -10**9, np.int32)
    total = np.zeros(N, np.int32)
    best_end = np.full(N, -1, np.int32)
    last_win = np.full(N, -1, np.int32)
    for di, W in enumerate(winners):
        # Reset tickets that miss this draw so current_streak reflects the
        # actual run ending at the latest draw, not an older winning run.
        previous = streak[W].astype(np.int32).copy()
        streak.fill(0)
        if len(W) == 0:
            continue
        last_win[W] = di
        ns = np.where(last[W] == di - 1, previous + 1, 1)
        streak[W] = ns.astype(np.int16)
        last[W] = di
        total[W] += 1
        imp = ns > best[W]
        if imp.any():
            w = W[imp]
            best[w] = ns[imp].astype(np.int16)
            best_end[w] = di
    print(f'  lotto streaks done in {time.time()-t0:.0f}s', flush=True)
    del order, sorted_masks

    # top records: unrank mask -> combo via combos file is too big; store mask hex
    # instead reconstruct combo from mask bits (54 bits -> 6 numbers)
    def mask_to_combo(m):
        return tuple(v for v in range(1, 55) if (m >> (v - 1)) & 1)

    order_idx = np.lexsort((-best_end, -best.astype(np.int32), -total))[:TOP_N]
    recs = []
    for i in order_idx:
        i = int(i)
        # recover mask: need index->mask map; lotto_combos.npy has combos (N,6)
        be = int(best_end[i])
        b = int(best[i])
        lw = int(last_win[i])
        recs.append({
            'idx': i,
            'total_wins': int(total[i]),
            'best_streak': b,
            'streak_start': dates[be - b + 1] if be >= 0 and b > 0 else None,
            'streak_end': dates[be] if be >= 0 else None,
            'last_win': dates[lw] if lw >= 0 else None,
            'drought': (len(dates) - 1 - lw) if lw >= 0 else len(dates),
            'current_streak': int(streak[i]),
        })
    # fill ticket strings from combos npy (memmap, random access)
    combos = np.load(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  '_archive', 'lotto_combos.npy'), mmap_mode='r')
    for rec in recs:
        c = combos[rec.pop('idx')]
        rec['ticket'] = ','.join(map(str, c.tolist()))
    return {
        'name': 'Lotto Texas', 'type': 'numbers', 'pick': '6/54',
        'n_tickets': N, 'n_draws': len(dates),
        'dates': dates, 'win_rule': 'match >= 4 (post-2006)',
        'top': recs,
    }


def unrank_lex(rank, comb, P, n=54, k=6):
    """Inverse of lex_rank."""
    out = []
    prev = 0
    r = int(rank)
    for i in range(k):
        acc = 0
        y = prev + 1
        while True:
            cc = int(comb[n - y, k - 1 - i]) if n - y >= k - 1 - i else 0
            if r < acc + cc:
                out.append(y)
                r -= acc
                prev = y
                break
            acc += cc
            y += 1
    return tuple(out)


# ---------- All or Nothing leftover pool ----------

def aon():
    draws, dates = load_draws(
        ['aon_morning.csv', 'aon_day.csv', 'aon_evening.csv', 'aon_night.csv'], 12)
    # canonicalize: complement if lowest >= 2
    canon_draws = []
    for _, nums in draws:
        s = sorted(nums)
        if s[0] >= 2:
            comp = tuple(sorted(set(range(1, 25)) - set(s)))
            canon_draws.append(comp)
        else:
            canon_draws.append(tuple(s))
    # load leftover pool (canonical half, contains 1)
    pool = []
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'aon_stacked_remaining.txt')
    if not os.path.exists(path):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'aon_6by6_sorted.txt')
    for line in open(path):
        line = line.strip()
        if line:
            pool.append(tuple(int(x) for x in line.split(',')))
    pool = [c for c in pool if 1 in c]  # canonical half only
    masks = np.array([sum(1 << (v - 1) for v in c) for c in pool], np.uint32)
    winners = []
    for nums in canon_draws:
        dm = sum(1 << (v - 1) for v in nums)
        m = np.bitwise_count(masks & np.uint32(dm))
        # e = |12 - k| <= 2  =>  k >= 10 or k <= 2
        winners.append(np.nonzero((m >= 10) | (m <= 2))[0].astype(np.int64))
    streak, best, total, best_end = run_streaks(len(pool), winners, dates)
    last_win = np.full(len(pool), -1, np.int32)
    for di, W in enumerate(winners):
        last_win[W] = di
    tix = [','.join(map(str, c)) for c in pool]
    return {
        'name': 'All or Nothing', 'type': 'numbers', 'pick': '12/24',
        'n_tickets': len(pool), 'n_draws': len(canon_draws),
        'dates': dates, 'win_rule': 'e <= 2 (any prize)',
        'top': top_records('All or Nothing', tix, streak, best, total, best_end, last_win, dates),
    }


def main():
    t0 = time.time()
    games = []

    def emit(fn, label):
        print(f'[{label}]', flush=True)
        games.append(fn())
        print(f'  done {time.time()-t0:.0f}s', flush=True)

    emit(lambda: digit_game('Pick 3 Morning', ['pick3morning.csv'], 3), 'pick3 morning')
    emit(lambda: digit_game('Pick 3 Day', ['pick3day.csv'], 3), 'pick3 day')
    emit(lambda: digit_game('Pick 3 Evening', ['pick3evening.csv'], 3), 'pick3 evening')
    emit(lambda: digit_game('Pick 3 Night', ['pick3night.csv'], 3), 'pick3 night')
    emit(lambda: digit_game('Daily 4 Morning', ['daily4morning.csv'], 4), 'daily4 morning')
    emit(lambda: digit_game('Daily 4 Day', ['daily4day.csv'], 4), 'daily4 day')
    emit(lambda: digit_game('Daily 4 Evening', ['daily4evening.csv'], 4), 'daily4 evening')
    emit(lambda: digit_game('Daily 4 Night', ['daily4night.csv'], 4), 'daily4 night')
    emit(cashfive, 'cashfive')
    emit(twostep, 'twostep')
    emit(lotto, 'lotto')
    emit(aon, 'aon')

    out = {
        'generated': time.strftime('%Y-%m-%d %H:%M'),
        'games': games,
    }
    with open(OUT, 'w') as f:
        json.dump(out, f)
    print(f'wrote {OUT} in {time.time()-t0:.0f}s')


if __name__ == '__main__':
    main()
