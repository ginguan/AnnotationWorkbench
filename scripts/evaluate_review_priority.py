"""Compare full second-review queues across fixed modeled time checkpoints."""
import hashlib
import json
from collections import Counter
from evaluate_memerag_transfer import MEMERAG_SHA, evaluation_rows
from evaluate_review_routing import (
    DATA_SHA, ROOT, SEEDS, candidate_rows, fit, review_sequence, rows_from_parquet,
)

# Minutes are assumptions, not observations. Every disagreement pays adjudication.
REVIEW_MIN, ADJUDICATE_MIN = 2, 4
CHECKPOINTS = (30, 60, 120)

def completed_by(rows, order, checkpoint):
    elapsed = reviews = resolved = adjudications = 0
    for index in order:
        row = rows[index]
        cost = REVIEW_MIN + ADJUDICATE_MIN * row["second"]
        if elapsed + cost > checkpoint:
            # The review or its immediate simulated adjudication is still in flight.
            break
        elapsed += cost
        reviews += 1
        adjudications += row["second"]
        resolved += row["second"] * row["reference"]
    return {"reviews": reviews, "resolved": resolved, "adjudications": adjudications}

def compare(rows, scores):
    out = []
    for budget in CHECKPOINTS:
        totals = {}
        for name, ranking in [("random_order", None), ("priority_order", scores)]:
            counts = Counter()
            for seed in SEEDS:
                counts.update(completed_by(rows, review_sequence(len(rows), seed, ranking), budget))
            totals[name] = {k: v/len(SEEDS) for k,v in counts.items()}
        out.append({"modeled_minutes": budget, **totals})
    return out

def evaluate(source, external):
    train, valid, test = (candidate_rows(source, k) for k in ("train", "valid", "test"))
    held_out = {r["group"] for r in valid + test}
    train = [r for r in train if r["group"] not in held_out]
    test = [dict(r, reference=r["independent"]) for r in test if r["independent"] is not None]
    recovery = fit(train, [r["second"] * r["reference"] for r in train])
    escalation = fit(train, [r["second"] for r in train])
    def score(rows):
        x = [r["features"] for r in rows]
        return list(recovery.predict_proba(x)[:,1] / (1+2*escalation.predict_proba(x)[:,1]))
    groups = [("TRIVIA+ independent votes",test)]
    groups += [(f"MEMERAG-Ext slots {a}/{b}", evaluation_rows(external,a,b))
               for a,b in [(0,1),(1,2),(2,3),(3,4),(4,0)]]
    return {
        "assumed_minutes": {"review": REVIEW_MIN, "adjudication": ADJUDICATE_MIN},
        "comparisons": [{"cohort":name,"cases":len(rows),
                         "findable_by_full_second_pass":sum(r["second"]*r["reference"] for r in rows),
                         "checkpoints":compare(rows, score(rows))} for name,rows in groups],
    }

if __name__ == "__main__":
    a,b = ROOT/".local/triviaplus_dataset.parquet", ROOT/".local/memerag-ext-en.jsonl"
    for path,sha in [(a,DATA_SHA),(b,MEMERAG_SHA)]:
        if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            raise SystemExit(f"Unexpected release for {path.name}")
    source,_ = rows_from_parquet(a)
    external = [json.loads(line) for line in b.read_text().splitlines() if line]
    out = json.dumps(evaluate(source,external),indent=2)+"\n"
    (ROOT/".local/review-priority-report.json").write_text(out)
    print(out)
