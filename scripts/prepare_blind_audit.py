"""Prepare a mixed blind audit packet from a frozen, local candidate batch."""
import argparse
import json
import random
import uuid
from pathlib import Path
from plan_skip_audit import audit_size

FIELDS = ("question", "answer", "passages")

def prepare(rows, cap, controls, rng=None):
    if type(controls) is not int or controls < 1:
        raise ValueError("At least one routed control is required for a mixed packet")
    if any(not isinstance(r.get("id"), str) or not r["id"].strip()
           or type(r.get("skipped")) is not bool
           or any(not isinstance(r.get(k), str) or not r[k].strip()
                  for k in ("question", "answer"))
           or not isinstance(r.get("passages"), list) or not r["passages"]
           or any(not isinstance(s, str) or not s.strip() for s in r["passages"])
           for r in rows):
        raise ValueError("Every case needs an ID, routing flag, question, answer and textual passages")
    if len({r["id"] for r in rows}) != len(rows):
        raise ValueError("Duplicate case ID")
    rng = random.SystemRandom() if rng is None else rng
    skipped = [r for r in rows if r["skipped"]]
    routed = [r for r in rows if not r["skipped"]]
    count = audit_size(len(skipped), cap)
    if controls > len(routed):
        raise ValueError("Not enough routed controls; do not silently export a skips-only packet")
    chosen = rng.sample(skipped, count) + rng.sample(routed, controls)
    rng.shuffle(chosen)
    packet, key = [], {}
    for row in chosen:
        token = uuid.uuid4().hex
        packet.append({"blind_id": token, **{k: row[k] for k in FIELDS}})
        key[token] = {"case_id": row["id"], "skipped": row["skipped"]}
    return packet, {"cap": cap, "alpha": .05, "skipped_population": len(skipped),
                    "sampled_skips": count, "sampled_controls": controls, "key": key}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Local JSONL (never send the input to reviewers)")
    parser.add_argument("output", type=Path, help="New private batch directory")
    parser.add_argument("--cap", type=float, default=.05)
    parser.add_argument("--controls", type=int, default=5)
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.input.read_text().splitlines() if line.strip()]
    packet, key = prepare(rows, args.cap, args.controls)
    args.output.mkdir(mode=0o700)
    private = args.output / "coordinator-only"
    private.mkdir(mode=0o700)
    (private / "key.json").write_text(json.dumps(key, indent=2) + "\n")
    (args.output / "reviewer.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in packet))

if __name__ == "__main__":
    main()
