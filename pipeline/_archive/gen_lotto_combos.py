#!/usr/bin/env python3
"""Generate all C(54,6) = 25,827,165 Lotto Texas combos.

Writes:
  lotto_combos.txt   - one combo per line, comma-separated
  lotto_combos.npy   - (N,6) uint8 array
  lotto_masks.npy    - (N,) uint64 bitmasks (54 bits -> uint64)
"""

import time
from itertools import combinations

import numpy as np

N = 25_827_165
CHUNK = 1_000_000


def main():
    t0 = time.time()
    combos = np.empty((N, 6), dtype=np.uint8)
    masks = np.empty(N, dtype=np.uint64)
    i = 0
    buf = []
    with open("lotto_combos.txt", "w") as f:
        for c in combinations(range(1, 55), 6):
            buf.append(",".join(map(str, c)) + "\n")
            combos[i] = c
            m = 0
            for n in c:
                m |= 1 << (n - 1)
            masks[i] = m
            i += 1
            if len(buf) >= CHUNK:
                f.write("".join(buf))
                buf.clear()
                if i % CHUNK == 0 or i == N:
                    print(f"{i:,}/{N:,} ({time.time()-t0:.0f}s)", flush=True)
        if buf:
            f.write("".join(buf))
    np.save("lotto_combos.npy", combos)
    np.save("lotto_masks.npy", masks)
    print(f"done {i:,} combos in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
