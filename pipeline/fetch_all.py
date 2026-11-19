#!/usr/bin/env python3
"""Refresh all draw CSVs: Texas Lottery games + Powerball / Mega Millions."""
import os, tempfile, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'data')
os.makedirs(DATA, exist_ok=True)

TX = "https://www.texaslottery.com/export/sites/lottery/Games/{g}/Winning_Numbers/{f}"
FILES = {
    'All_or_Nothing': {'allornothingmorning.csv': 'aon_morning.csv',
                       'allornothingday.csv': 'aon_day.csv',
                       'allornothingevening.csv': 'aon_evening.csv',
                       'allornothingnight.csv': 'aon_night.csv'},
    'Pick_3': {'pick3morning.csv': 'pick3morning.csv', 'pick3day.csv': 'pick3day.csv',
               'pick3evening.csv': 'pick3evening.csv', 'pick3night.csv': 'pick3night.csv'},
    'Daily_4': {'daily4morning.csv': 'daily4morning.csv', 'daily4day.csv': 'daily4day.csv',
                'daily4evening.csv': 'daily4evening.csv', 'daily4night.csv': 'daily4night.csv'},
    'Cash_Five': {'cashfive.csv': 'cashfive.csv'},
    'Texas_Two_Step': {'texastwostep.csv': 'texastwostep.csv'},
    'Lotto_Texas': {'lottotexas.csv': 'lottotexas.csv'},
}
OTHER = {
    'powerball.csv': 'https://louisianalottery.com/csv/powerball.csv',
    'megamillions.csv': 'https://louisianalottery.com/csv/mega-millions.csv',
}


def download_atomic(url, dst):
    """Download to a temporary sibling file; replace the prior CSV only on success."""
    fd, tmp = tempfile.mkstemp(prefix='.download-', suffix='.tmp', dir=DATA)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with os.fdopen(fd, 'wb') as out:
            with urllib.request.urlopen(req, timeout=60) as response:
                payload = response.read()
            if not payload:
                raise ValueError('empty response')
            if payload.lstrip().lower().startswith((b'<!doctype html', b'<html')):
                raise ValueError('received HTML instead of CSV data')
            out.write(payload)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, dst)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main():
    failures = []
    jobs = []
    for game, files in FILES.items():
        for remote, local in files.items():
            jobs.append((local, TX.format(g=game, f=remote)))
    jobs.extend(OTHER.items())

    for local, url in jobs:
        dst = os.path.join(DATA, local)
        try:
            download_atomic(url, dst)
            print(f'OK  {local}')
        except Exception as e:
            failures.append((local, str(e)))
            print(f'FAIL {local}: {e}')

    if failures:
        names = ', '.join(name for name, _ in failures)
        raise SystemExit(f'{len(failures)} of {len(jobs)} downloads failed; refusing to build/publish stale data: {names}')

    print(f'All {len(jobs)} source files downloaded successfully.')


if __name__ == '__main__':
    main()
