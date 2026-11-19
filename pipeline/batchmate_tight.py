#!/usr/bin/env python3
"""Harvest generated ticket batches into tight_tickets.json for the app.

Per ticket:
  best      = closest-ever match vs history, e.g. '11/12', '4/5+B'
  best_date = LATEST date where that best match occurred
  asof      = latest draw date in that game's data
  last      = match vs the single most recent draw
  last_draw = that draw's numbers (display string)
"""
import csv, os, re, json
from collections import Counter
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'data')
OUT = []


def add(game, ticket, detail, best='', best_date='', asof='', last='', last_draw='', sess='', remake='', last_win=True):
    OUT.append({'game': game, 'ticket': ticket, 'detail': detail,
                'best': best, 'best_date': best_date, 'asof': asof,
                'last': last, 'last_draw': last_draw, 'sess': sess,
                'remake': remake, 'last_win': last_win})


def fmt_draw(d, k, bonus=False):
    return ','.join(map(str, d[:k])) + (f' + {d[k]}' if bonus else '')


def last_aon(ticket, draw):
    nums = [int(x) for x in ticket.split(',')]
    tm = sum(1 << (v - 1) for v in nums)
    dm = sum(1 << (v - 1) for v in draw)
    k = (tm & dm).bit_count()
    return f'{k if k >= 6 else 12 - k}/12'


def last_digits(ticket, draw):
    t = Counter(int(c) for c in ticket)
    return f'{sum((Counter(draw) & t).values())}/{len(draw)}'


def last_combo(ticket, draw, k, bonus=False):
    parts = ticket.split(' + ')
    nums = [int(x) for x in parts[0].split(',')]
    b = int(parts[1]) if bonus and len(parts) > 1 else None
    dm = sum(1 << (v - 1) for v in draw[:k])
    tm = sum(1 << (v - 1) for v in nums)
    s = f'{(tm & dm).bit_count()}/{k}'
    if bonus and b is not None and draw[k] == b:
        s += '+B'
    return s


# ---------- win-tier adjusters: edit failing combos to reach lowest prize on latest draw ----------

def _swap_to(T, Dm, target_inter, universe):
    """Edit set T so |T & Dm| == target_inter (or as close as possible)."""
    T = set(T); Dm = set(Dm)
    cur = len(T & Dm)
    rem = sorted(T - Dm)
    add_pool = sorted(Dm - T)
    out = set(T)
    if cur < target_inter:
        need = target_inter - cur
        for v in add_pool[:need]:
            out.add(v)
        for v in rem[:need]:
            out.discard(v)
    elif cur > target_inter:
        need = cur - target_inter
        matched = sorted(T & Dm)
        undrawn = sorted(universe - Dm - T)
        for v in matched[:need]:
            out.discard(v)
        for v in undrawn[:need]:
            out.add(v)
    return sorted(out)


def _enforce_one(nums, draw_set):
    if 1 in nums:
        return nums
    nodraw = [v for v in nums if v not in draw_set]
    drop = nodraw[-1] if nodraw else nums[-1]
    nums = [v for v in nums if v != drop]
    nums.append(1)
    return sorted(nums)


def adjust_digits(ticket, draws):
    draw = draws[-1][2]
    won = Counter(int(c) for c in ticket) == Counter(draw)
    return ''.join(str(d) for d in sorted(draw)), won


def adjust_combo(ticket, draws, k, need_mains, bonus=False, bonus_mains=None):
    d = draws[-1][2]
    Dm = set(d[:k])
    Db = d[k] if bonus else None
    parts = ticket.split(' + ')
    nums = [int(x) for x in parts[0].split(',')]
    b = int(parts[1]) if bonus and len(parts) > 1 else None
    T = set(nums)
    cur = len(T & Dm)
    won = cur >= need_mains or (bonus_mains is not None and cur >= bonus_mains and b == Db)
    edits_a = max(0, need_mains - cur)
    edits_b = None
    if bonus_mains is not None:
        m_need = max(0, bonus_mains - cur)
        b_fix = 0 if b == Db else 1
        edits_b = m_need + b_fix
    if edits_b is not None and edits_b < edits_a:
        new_nums = _swap_to(nums, Dm, bonus_mains, set(range(1, 100)))
        new_b = Db
    else:
        new_nums = _swap_to(nums, Dm, need_mains, set(range(1, 100)))
        new_b = b
    new_nums = _enforce_one(new_nums, Dm)
    out = ','.join(map(str, new_nums))
    if bonus:
        out += f' + {new_b}'
    return out, won


def adjust_aon(ticket, draws):
    d = draws[-1][2]
    D = set(d)
    U = set(range(1, 25))
    T = set(int(x) for x in ticket.split(','))
    k = len(T & D)
    m = k if k >= 6 else 12 - k
    won = m >= 10
    e1 = max(0, 10 - k)
    e2 = max(0, k - 2)
    if e1 <= e2:
        new = _swap_to(sorted(T), D, 10, U)
    else:
        new = _swap_to(sorted(T), D, 2, U)
    new = _enforce_one(new, D)
    return ','.join(map(str, new)), won


# ---------- draw loaders -> [(date_key, date_str, nums)] ----------


def _mdy(r):
    y, m, d = int(r[3]), int(r[1]), int(r[2])
    return (y, m, d), f'{m}/{d}/{y}'


def load_aon():
    draws = []
    for s in ['morning', 'day', 'evening', 'night']:
        for r in csv.reader(open(os.path.join(DATA, f'aon_{s}.csv'))):
            if len(r) < 16:
                continue
            dk, ds = _mdy(r)
            draws.append((dk, ds, tuple(sorted(int(x) for x in r[4:16]))))
    draws.sort(key=lambda x: x[0])
    return draws


def load_simple(fname, n):
    draws = []
    for r in csv.reader(open(os.path.join(DATA, fname))):
        if len(r) < 4 + n:
            continue
        dk, ds = _mdy(r)
        draws.append((dk, ds, tuple(int(x) for x in r[4:4 + n])))
    draws.sort(key=lambda x: x[0])
    return draws


def load_pbmm(fname, cutoff):
    draws = []
    for r in csv.reader(open(os.path.join(DATA, fname))):
        if len(r) < 7 or not re.match(r'^\d{4}-\d{2}-\d{2}$', r[0]) or r[0] < cutoff:
            continue
        y, m, d = int(r[0][:4]), int(r[0][5:7]), int(r[0][8:10])
        draws.append(((y, m, d), f'{m}/{d}/{y}', tuple(int(x) for x in r[1:7])))
    draws.sort(key=lambda x: x[0])
    return draws


# ---------- best-match scorers ----------

AON_DRAWS = []


def best_aon(ticket):
    nums = [int(x) for x in ticket.split(',')]
    tm = sum(1 << (v - 1) for v in nums)
    best = -1
    bdate = ''
    for dk, dstr, d in AON_DRAWS:
        dm = sum(1 << (v - 1) for v in d)
        k = (tm & dm).bit_count()
        m = k if k >= 6 else 12 - k
        if m >= best:  # >= keeps LATEST date at best match
            best, bdate = m, dstr
    return f'{best}/12', bdate


def best_digits(ticket, draws, width):
    t = Counter(int(c) for c in ticket)
    best = -1
    bdate = ''
    for dk, dstr, d in draws:
        m = sum((Counter(d) & t).values())
        if m >= best:
            best, bdate = m, dstr
    return f'{best}/{width}', bdate


def best_combo(ticket, draws, k, has_bonus=False):
    parts = ticket.split(' + ')
    nums = tuple(int(x) for x in parts[0].split(','))
    bonus = int(parts[1]) if has_bonus and len(parts) > 1 else None
    cm = 0
    for v in nums:
        cm |= 1 << (v - 1)
    best_key = (-1, False)
    best_inter = -1
    bdate = ''
    for dk, dstr, d in draws:
        dm = 0
        for v in d[:k]:
            dm |= 1 << (v - 1)
        inter = (cm & dm).bit_count()
        bb = bonus is not None and d[k] == bonus
        key = (inter, bb)
        if key >= best_key:  # >= keeps LATEST date at best (inter, bonus)
            best_key, bdate = key, dstr
        if inter > best_inter:
            best_inter = inter
    s = f'{best_inter}/{k}'
    if has_bonus:
        s += '+B' if best_key[1] else ''
    return s, bdate


# ---------- file parsers ----------

def parse_align_auto():
    path = os.path.join(HERE, 'aon_align_auto.txt')
    if not os.path.exists(path):
        return
    stream = W = stats = None
    asof = AON_DRAWS[-1][1] if AON_DRAWS else ''
    last_draw = AON_DRAWS[-1][2] if AON_DRAWS else ()
    last_str = ','.join(map(str, last_draw)) if last_draw else ''
    for line in open(path):
        m = re.match(r'\[(\w+) W=(\d+)\]', line)
        if m:
            stream, W = m.group(1), m.group(2)
            continue
        m = re.search(r'e1=(\d+) e2=(\d+) jack=(\d+)', line)
        if m:
            stats = f'e1={m.group(1)} e2={m.group(2)}'
            continue
        m = re.match(r'\s*([\d,]+)\s*$', line)
        if m and stream:
            b, bd = best_aon(m.group(1))
            rm, lw = adjust_aon(m.group(1), AON_DRAWS)
            add('All or Nothing', m.group(1), f'{stream} W={W} {stats}',
                b, bd, asof, last_aon(m.group(1), last_draw), last_str,
                remake=rm, last_win=lw)
            stream = None


def parse_aon_rolling():
    path = os.path.join(HERE, 'aon_rolling_tickets.txt')
    if not os.path.exists(path):
        return
    asof = AON_DRAWS[-1][1] if AON_DRAWS else ''
    last_draw = AON_DRAWS[-1][2] if AON_DRAWS else ()
    last_str = ','.join(map(str, last_draw)) if last_draw else ''
    for line in open(path):
        if 'e1=' not in line:
            continue
        m = re.match(r'\s*([\d,]+)\s+#\s*e1=(\d+) e2=\s*(\d+) jack=(\d+) sum=(\d+)\s*(\S+)', line)
        if m:
            b, bd = best_aon(m.group(1))
            rm, lw = adjust_aon(m.group(1), AON_DRAWS)
            add('All or Nothing', m.group(1),
                f'e1={m.group(2)} e2={m.group(3)} {m.group(6)}',
                b, bd, asof, last_aon(m.group(1), last_draw), last_str,
                remake=rm, last_win=lw)


def parse_rolling(fname, game, draws, k, bonus=False, sess='', need_mains=0, bonus_mains=None, digits=False):
    path = os.path.join(HERE, fname)
    if not os.path.exists(path):
        return
    asof = draws[-1][1] if draws else ''
    last_draw = draws[-1][2] if draws else ()
    if last_draw:
        last_str = fmt_draw(last_draw, k, bonus) if bonus else (
            ''.join(map(str, last_draw)) if k == len(last_draw) and k <= 4 else
            fmt_draw(last_draw, k, bonus))
    else:
        last_str = ''
    for line in open(path):
        line = line.strip()
        m = re.match(r'([\d,]*\d,\d[\d,]*(?: \+ \d+)?)\s+#\s*(.*)', line)
        if m:
            b, bd = best_combo(m.group(1), draws, k, bonus)
            rm, lw = adjust_combo(m.group(1), draws, k, need_mains, bonus, bonus_mains) if need_mains else ('', True)
            add(game, m.group(1), m.group(2).strip(),
                b, bd, asof, last_combo(m.group(1), last_draw, k, bonus), last_str, sess,
                remake=rm, last_win=lw)
            continue
        m = re.match(r'(\d{3,4})\s+#\s*(.*)', line)
        if m:
            b, bd = best_digits(m.group(1), draws, len(m.group(1)))
            rm, lw = adjust_digits(m.group(1), draws) if digits else ('', True)
            add(game, m.group(1), m.group(2).strip(),
                b, bd, asof, last_digits(m.group(1), last_draw), last_str, sess,
                remake=rm, last_win=lw)


def main():
    global AON_DRAWS
    AON_DRAWS = load_aon()

    parse_align_auto()
    parse_aon_rolling()

    for sess in ['morning', 'day', 'evening', 'night']:
        d3 = load_simple(f'pick3{sess}.csv', 3)
        parse_rolling(f'rolling_pick_3_{sess}.txt', 'Pick 3', d3, 3, sess=sess, digits=True)
        d4 = load_simple(f'daily4{sess}.csv', 4)
        parse_rolling(f'rolling_daily_4_{sess}.txt', 'Daily 4', d4, 4, sess=sess, digits=True)

    cf = load_simple('cashfive.csv', 5)
    parse_rolling('rolling_cash_five.txt', 'Cash Five', cf, 5, need_mains=3)

    ts = load_simple('texastwostep.csv', 5)
    parse_rolling('rolling_texas_two_step.txt', 'Texas Two Step', ts, 4, bonus=True, need_mains=3, bonus_mains=2)

    lt = load_simple('lottotexas.csv', 6)
    parse_rolling('rolling_lotto_texas.txt', 'Lotto Texas', lt, 6, need_mains=4)

    pb = load_pbmm('powerball.csv', '2015-10-07')
    parse_rolling('rolling_powerball.txt', 'Powerball', pb, 5, bonus=True, need_mains=4, bonus_mains=3)

    mm = load_pbmm('megamillions.csv', '2020-03-24')
    parse_rolling('rolling_mega_millions.txt', 'Mega Millions', mm, 5, bonus=True, need_mains=4, bonus_mains=3)

    seen = set()
    uniq = []
    for t in OUT:
        k = (t['game'], t.get('sess', ''), t['ticket'])
        if k not in seen:
            seen.add(k)
            uniq.append(t)
    with open(os.path.join(HERE, 'tight_tickets.json'), 'w') as f:
        json.dump({'generated': datetime.now().isoformat(timespec='seconds'),
                   'tickets': uniq}, f, indent=1)
    print(f'{len(uniq)} tight tickets -> tight_tickets.json')


if __name__ == '__main__':
    main()
