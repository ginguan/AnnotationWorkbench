"""Fixed-budget follow-up replay evaluated against additional human voters only."""
import json
import hashlib
from evaluate_review_routing import (
    ROOT, DATA_SHA, add_cost, budget_index, candidate_rows, choose_budget,
    curves, fit, rows_from_parquet,
)

def evaluate(rows):
    train, valid, test = (candidate_rows(rows, key) for key in ("train", "valid", "test"))
    test_groups = {r["group"] for r in test}
    valid = [r for r in valid if r["group"] not in test_groups]
    held_out = test_groups | {r["group"] for r in valid}
    train = [r for r in train if r["group"] not in held_out]
    valid = [r for r in valid if r["independent"] is not None]
    test = [r for r in test if r["independent"] is not None]

    recovery = fit(train, [r["second"] * r["reference"] for r in train])
    escalation = fit(train, [r["second"] for r in train])
    def score(subset, weight):
        features = [r["features"] for r in subset]
        return list(recovery.predict_proba(features)[:, 1]
                    / (1 + weight * escalation.predict_proba(features)[:, 1]))

    validate_random = curves(valid, reference="independent")
    test_random = curves(test, reference="independent")
    results = []
    for weight in (1, 2, 4):
        validate_risk = curves(valid, score(valid, weight), reference="independent")
        test_risk = curves(test, score(test, weight), reference="independent")
        benchmark = validate_random[budget_index(validate_random, .5)]
        fraction = choose_budget(validate_risk, benchmark, weight) / len(valid)
        results.append({
            "adjudication_cost": weight,
            "validation_budget_fraction": fraction,
            "validation_random": add_cost(benchmark, weight),
            "validation_risk": add_cost(validate_risk[budget_index(validate_risk, fraction)], weight),
            "test_random": add_cost(test_random[budget_index(test_random, .5)], weight),
            "test_risk": add_cost(test_risk[budget_index(test_risk, fraction)], weight),
            "test_full_second_pass": add_cost(test_random[-1], weight),
        })
    return {"candidate_counts": {"training": len(train), "validation": len(valid), "test": len(test)},
            "test_initial_misses": test_random[0]["missed"], "comparisons": results}

if __name__ == "__main__":
    source = ROOT / ".local/triviaplus_dataset.parquet"
    if hashlib.sha256(source.read_bytes()).hexdigest() != DATA_SHA:
        raise SystemExit("Dataset does not match pinned release")
    rows, _ = rows_from_parquet(source)
    aggregate = json.dumps(evaluate(rows), indent=2) + "\n"
    (ROOT / ".local/triviaplus-independent-report.json").write_text(aggregate)
    print(aggregate)
