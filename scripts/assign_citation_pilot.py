"""Assign pairs of distinct cases to both citation pilot modes, locally."""
import argparse
import csv
import json
import random

FIELDS = ("reviewer", "pair", "case", "mode", "order")


def assign(pairs, reviewers, seed=0):
    """Balance case-to-mode and mode order in blocks of four reviewers."""
    if not pairs or not reviewers or len(set(reviewers)) != len(reviewers):
        raise ValueError("Provide nonempty pairs and unique reviewers")
    pair_ids, cases = set(), set()
    for pair in pairs:
        ident, first, second = (pair[k] for k in ("pair", "case_a", "case_b"))
        if (not all(isinstance(value, str) and value.strip() for value in (ident, first, second))
                or ident in pair_ids or first == second or first in cases or second in cases):
            raise ValueError("Use unique pairs and distinct case IDs")
        pair_ids.add(ident)
        cases.update((first, second))
    pair_index = {ident: i for i, ident in enumerate(sorted(pair_ids))}
    rng = random.Random(seed)
    people = sorted(reviewers)
    rng.shuffle(people)
    schedule = []
    for index, reviewer in enumerate(people):
        order = list(pairs)
        rng.shuffle(order)
        for pair in order:
            # Index the unswapped pair by ID order, independently of its session position.
            variant = (index + pair_index[pair["pair"]]) % 4
            baseline, jump = pair["case_a"], pair["case_b"]
            if variant & 1:
                baseline, jump = jump, baseline
            modes = [("baseline", baseline), ("jump", jump)]
            if variant & 2:
                modes.reverse()
            schedule.extend(dict(reviewer=reviewer, pair=pair["pair"], case=case,
                                 mode=mode, order=position)
                            for position, (mode, case) in enumerate(modes, 1))
    return schedule


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", help="JSON array of objects with pair, case_a and case_b")
    parser.add_argument("output_csv", help="new coordinator-only CSV")
    parser.add_argument("--reviewer", action="append", required=True)
    parser.add_argument("--seed", type=int, default=0)
    opts = parser.parse_args()
    try:
        with open(opts.manifest, encoding="utf-8") as stream:
            rows = assign(json.load(stream), opts.reviewer, opts.seed)
        with open(opts.output_csv, "x", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.error(str(exc))
