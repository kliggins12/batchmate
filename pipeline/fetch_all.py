#!/usr/bin/env python3
"""Refresh all draw CSVs: Texas Lottery games + AoN + PB/MM (Louisiana)."""
import os, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'data')
os.makedirs(DATA, exist_ok=True)

TX = "https://www.texaslottery.com/export/sites/lottery/Games/{g}/Winning_Numbers/{f}"
FILES = {
    # game dir, csv filename -> local name
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

def main():
    for game, files in FILES.items():
        for remote, local in files.items():
            url = TX.format(g=game, f=remote)
            dst = os.path.join(DATA, local)
            try:
                urllib.request.urlretrieve(url, dst)
                print(f'OK  {local}')
            except Exception as e:
                print(f'FAIL {local}: {e}')
    for local, url in OTHER.items():
        dst = os.path.join(DATA, local)
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as r, open(dst, 'wb') as f:
                f.write(r.read())
            print(f'OK  {local}')
        except Exception as e:
            print(f'FAIL {local}: {e}')

if __name__ == '__main__':
    main()
