"""Apply the TRIVIA+-trained scorer unchanged to a separate MEMERAG-Ext release."""
import hashlib
import json
from collections import Counter
from evaluate_review_routing import (
    ROOT, DATA_SHA, add_cost, budget_index, candidate_rows, curves, features, fit, rows_from_parquet,
)

MEMERAG_SHA = "955020631266924c31a81691ca29f0f93e7e678e902b6135a9bc134f898f8f18"
FROZEN_FRACTION = 30 / 124
LABELS = {"Supported": 0, "Not Supported": 1}

def evaluation_rows(data, first=0, second=1):
    reserved = [k for k in range(5) if k not in (first, second)]
    if len({r["query_id"] for r in data}) != len(data):
        raise ValueError("Duplicate query")
    rows = []
    for r in data:
        sentences = r["answer"]
        if not sentences or any(len(s["factuality"]) != 5 for s in sentences):
            raise ValueError("Expected five faithfulness vote slots per sentence")
        slots = [any(LABELS[s["factuality"][k]] for s in sentences) for k in range(5)]
        if slots[first]:
            continue
        article = "\n".join(p["text"] for p in r["context"])
        answer = " ".join(s["sentence"] for s in sentences)
        x = features(article, r["query"], answer, "memerag", "unknown", [""] * len(sentences))
        # Unknown categories activate no training column; the unavailable fraction is omitted.
        del x["first_supplementary_fraction"]
        rows.append({"features": x, "reference": int(sum(slots[k] for k in reserved) >= 2),
                     "second": int(slots[second])})
    return rows

def evaluate(train_rows, data):
    train, valid, test = (candidate_rows(train_rows, s) for s in ("train", "valid", "test"))
    held_out = {r["group"] for r in valid + test}
    train = [r for r in train if r["group"] not in held_out]
    recovery = fit(train, [r["second"] * r["reference"] for r in train])
    escalation = fit(train, [r["second"] for r in train])
    output = []
    for first, second in [(0,1), (1,2), (2,3), (3,4), (4,0)]:
        rows = evaluation_rows(data, first, second)
        inputs = [r["features"] for r in rows]
        score = recovery.predict_proba(inputs)[:,1] / (1 + 2*escalation.predict_proba(inputs)[:,1])
        random = curves(rows)
        risk = curves(rows, list(score))
        budget = budget_index(random, FROZEN_FRACTION)
        output.append({"vote_slots": [first,second], "first_pass_approvals": len(rows),
                       "initial_misses": random[0]["missed"],
                       "random_same_budget": add_cost(random[budget],2),
                       "risk_plus_audit_same_budget": add_cost(risk[budget],2),
                       "random_half": add_cost(random[budget_index(random,.5)],2)})
    return {"questions":len(data), "sentences":sum(len(r["answer"]) for r in data),
            "training_approvals":len(train), "budget_fraction":FROZEN_FRACTION,
            "comparisons":output}

if __name__ == "__main__":
    training = ROOT / ".local/triviaplus_dataset.parquet"
    external = ROOT / ".local/memerag-ext-en.jsonl"
    for path, sha in [(training,DATA_SHA),(external,MEMERAG_SHA)]:
        if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            raise SystemExit(f"Unexpected release for {path.name}")
    train, _ = rows_from_parquet(training)
    data = [json.loads(line) for line in external.read_text().splitlines() if line]
    report = json.dumps(evaluate(train, data), indent=2) + "\n"
    (ROOT / ".local/memerag-transfer-report.json").write_text(report)
    print(report)
