"""Score a local, counterbalanced citation-navigation timing pilot."""
import argparse
import csv
import json
import math
from statistics import mean, median

MODES = {"baseline", "jump"}


def score(rows):
    """Each reviewer sees two different matched cases per pair, one per arm."""
    pairs, seen = {}, set()
    for row in rows:
        reviewer, pair, case = (row[k].strip() for k in ("reviewer", "pair", "case"))
        mode, correct = row["mode"], row["correct"]
        active, rework = float(row["active_s"]), float(row["rework_s"])
        order = int(row["order"])
        if (not all((reviewer, pair, case)) or mode not in MODES
                or correct not in {"0", "1"} or order not in {1, 2}
                or not math.isfinite(active) or not math.isfinite(rework)
                or active <= 0 or rework < 0):
            raise ValueError("Invalid timing row")
        arm = pairs.setdefault((reviewer, pair), {})
        if (reviewer, case) in seen or mode in arm:
            raise ValueError("Repeated case or arm for reviewer")
        seen.add((reviewer, case))
        arm[mode] = (active + rework, correct == "0", order)
    if not pairs:
        raise ValueError("No timing rows")
    if any(set(p) != MODES or p["baseline"][2] == p["jump"][2] for p in pairs.values()):
        raise ValueError("Each pair needs both arms and distinct positions")
    savings = [p["baseline"][0] - p["jump"][0] for p in pairs.values()]
    return {
        "pairs": len(pairs),
        "reviewers": len({reviewer for reviewer, _ in pairs}),
        "jump_first_pairs": sum(p["jump"][2] == 1 for p in pairs.values()),
        "mean_paired_seconds_saved_including_rework": mean(savings),
        "median_paired_seconds_saved_including_rework": median(savings),
        "material_errors": {m: sum(p[m][1] for p in pairs.values()) for m in sorted(MODES)},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file")
    args = parser.parse_args()
    try:
        with open(args.csv_file, newline="", encoding="utf-8") as stream:
            print(json.dumps(score(csv.DictReader(stream)), indent=2))
    except (ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
