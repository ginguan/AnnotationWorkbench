"""Size a simple, uniform blind audit of a finite batch of skipped reviews."""
import argparse
from math import ceil, comb

def audit_size(population, cap, alpha=.05):
    if population < 1 or not 0 < cap < 1 or not 0 < alpha < 1:
        raise ValueError("positive population and cap/alpha strictly between 0 and 1 required")
    bad = ceil(population * cap)
    # At the threshold or worse, probability of zero hits falls as sample size grows.
    lo, hi = 0, population - bad + 1
    while lo < hi:
        draw = (lo + hi) // 2
        miss = comb(population - bad, draw) / comb(population, draw)
        if miss <= alpha:
            hi = draw
        else:
            lo = draw + 1
    return lo

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skipped", type=int)
    parser.add_argument("--cap", default=.05, type=float)
    args = parser.parse_args()
    print(audit_size(args.skipped, args.cap))
