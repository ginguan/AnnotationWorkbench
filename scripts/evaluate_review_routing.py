"""Offline TRIVIA+ replay. The output contains aggregate metrics, never raw text or votes."""
import argparse
import hashlib
import json
import math
import random
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_SHA = "fecd7a981778f6c09b35eb493f3fe76cddff81e268ae4a90711e4f2298fc383d"
SEEDS = tuple(range(64))
RATIOS = (1, 2, 4)
TEST_FRACTIONS = tuple(range(0, 101, 5))
COLS = ["article", "question", "answer", "source", "model", "split", "workerId",
        "response-level-labels-bin", "sentence-level-word-labels", "response_level_label_binary"]
WORDS = re.compile(r"[a-z]+|\d+(?:\.\d+)?", re.I)
NEG = {"no", "not", "never", "only", "without", "unless", "except"}
STOP = set("the a an of to in is was were be as and or for with on from that this it at by are has have".split())


def partition_reviews(n, key):
    """Frozen pseudo-assignment: publication does not guarantee chronological vote order."""
    if n < 2:
        raise ValueError("Not enough independent votes")
    generator = random.Random(int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big"))
    order = list(range(n))
    generator.shuffle(order)
    return order


def features(article, question, answer, source, model, first_sentences):
    """Only content and signals observable after the first review."""
    a = WORDS.findall(answer.lower())
    q = set(WORDS.findall(question.lower()))
    c = WORDS.findall(article.lower())
    ctx = set(c)
    core = {w for w in a if w not in STOP and w not in q}
    counts = Counter(c)
    numbers = {w for w in a if w[0].isdigit()}
    bigrams = set(zip(c, c[1:]))
    return {
        "source": source.replace("ms_marco", "msmarco"),
        "generator": model,
        "context_log_tokens": math.log1p(len(c)),
        "answer_log_tokens": math.log1p(len(a)),
        "answer_number_count": len(numbers),
        "unseen_number_fraction": len(numbers - ctx) / max(1, len(numbers)),
        "unseen_answer_terms": len(core - ctx) / max(1, len(core)),
        "mean_context_term_frequency": sum(math.log1p(counts[w]) for w in core) / max(1, len(core)),
        "unseen_answer_bigrams": sum(pair not in bigrams for pair in zip(a, a[1:])) / max(1, len(a)-1),
        "answer_negation": int(not NEG.isdisjoint(a)),
        "first_sentence_count": len(first_sentences),
        "first_supplementary_fraction": first_sentences.count("supplementary") / max(1, len(first_sentences)),
    }


def rows_from_parquet(path):
    import pyarrow.parquet as pq
    rows, excluded = [], Counter()
    for r in pq.read_table(path, columns=COLS).to_pylist():
        votes = r["response-level-labels-bin"]
        sentence_votes = r["sentence-level-word-labels"]
        workers = r["workerId"]
        if (len(votes) != len(set(workers)) or len(votes) != len(sentence_votes)
                or set(votes) - {"0", "1"}):
            excluded[r["split"]] += 1
            continue
        key = r["question"]+"\0"+r["answer"]+"\0"+r["model"]
        i, j, *reserved = partition_reviews(len(votes), key)
        row = {"group": hashlib.sha256(r["article"].encode()).hexdigest(), "split": r["split"], "first": int(votes[i]), "second": int(votes[j]),
               "reference": r["response_level_label_binary"], "independent": None,
               "features": features(r["article"], r["question"], r["answer"], r["source"],
                                    r["model"], sentence_votes[i])}
        if reserved:
            # Remaining voters only. Ties flagged as unsupported, like source's strict tie policy.
            # This is a response-vote sensitivity proxy, not the source's sentence aggregation.
            row["independent"] = int(sum(int(votes[k]) for k in reserved)*2 >= len(reserved))
        rows.append(row)
    return rows, dict(excluded)


def candidate_rows(rows, split):
    return [r for r in rows if r["split"] == split and r["first"] == 0]


def review_sequence(n, seed, ranking=None):
    ids = list(range(n))
    random.Random(seed).shuffle(ids)
    if ranking is None:
        return ids
    ordered = iter(sorted(ids, key=lambda i: -ranking[i]))
    audit = iter(ids)
    used = set()
    seq = []
    for slot in range(n):
        # One in ten, uniformly drawn from unselected rows; nested budget curve.
        pool = audit if (slot+1) % 10 == 0 else ordered
        pick = next(i for i in pool if i not in used)
        used.add(pick)
        seq.append(pick)
    return seq


def curves(rows, ranking=None, reference="reference"):
    n = len(rows)
    recovered = [0]* (n+1)
    adjudications = [0]* (n+1)
    misses = sum(r[reference] for r in rows)
    for seed in SEEDS:
        rec = adj = 0
        for b, i in enumerate(review_sequence(n, seed, ranking), 1):
            row = rows[i]
            adj += row["second"]
            rec += row["second"]*row[reference]
            recovered[b] += rec
            adjudications[b] += adj
    return [dict(reviews=b, recovered=recovered[b]/len(SEEDS), missed=misses-recovered[b]/len(SEEDS),
                 adjudications=adjudications[b]/len(SEEDS)) for b in range(n+1)]


def fit(train, target):
    from sklearn.feature_extraction import DictVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    model = make_pipeline(DictVectorizer(), StandardScaler(with_mean=False),
                          LogisticRegression(C=0.2, max_iter=1000))
    return model.fit([x["features"] for x in train], target)


def budget_index(curve, fraction):
    return round((len(curve)-1)*fraction)


def add_cost(m, ratio):
    return dict(m, workload=m["reviews"]+ratio*m["adjudications"])


def choose_budget(risk_curve, baseline, ratio):
    target = baseline["recovered"]
    return min((i for i,m in enumerate(risk_curve) if m["recovered"] >= target),
               key=lambda i:add_cost(risk_curve[i],ratio)["workload"])


def evaluate(rows):
    train, valid, test = (candidate_rows(rows, key) for key in ("train","valid","test"))
    # If source articles span publisher partitions, keep test intact and prevent text overlap.
    test_groups={r["group"] for r in test}
    valid=[r for r in valid if r["group"] not in test_groups]
    held_out=test_groups | {r["group"] for r in valid}
    train=[r for r in train if r["group"] not in held_out]
    recovered = fit(train, [r["second"]*r["reference"] for r in train])
    adjudicated = fit(train, [r["second"] for r in train])
    vr, tr = curves(valid), curves(test)
    vb = vr[budget_index(vr,.5)]
    tb = tr[budget_index(tr,.5)]
    result = {
        "data": "TRIVIA+ · human votes, offline observational replay",
        "seedCount": len(SEEDS), "sha256": DATA_SHA,
        "candidates": dict(train=len(train), valid=len(valid), test=len(test)),
        "initialTestMisses": sum(r["reference"] for r in test),
        "comparisons": [],
    }
    for ratio in RATIOS:
        def scores(subset):
            x = [r["features"] for r in subset]
            return list(recovered.predict_proba(x)[:,1] / (1+ratio*adjudicated.predict_proba(x)[:,1]))
        vcurve, tcurve = curves(valid,scores(valid)), curves(test,scores(test))
        pi = choose_budget(vcurve,vb,ratio)
        fraction = pi/len(valid)
        ti = budget_index(tcurve,fraction)
        comparison = dict(adjudicationCost=ratio, fractionFromValidation=fraction,
            random=add_cost(tb,ratio), risk=add_cost(tcurve[ti],ratio),
            riskSameReviewBudget=add_cost(tcurve[tb["reviews"]],ratio))
        if ratio == 2:
            result["curve"] = [dict(percent=p, random=add_cost(tr[budget_index(tr,p/100)],ratio),
                                   risk=add_cost(tcurve[budget_index(tcurve,p/100)],ratio)) for p in TEST_FRACTIONS]
            extra_test=[r for r in test if r["independent"] is not None]
            rr, sr=curves(extra_test,reference="independent"),curves(extra_test,scores(extra_test),reference="independent")
            result["independentSensitivity"] = dict(candidates=len(extra_test),
                initialMisses=sum(r["independent"] for r in extra_test),
                random=add_cost(rr[budget_index(rr,.5)],ratio),
                risk=add_cost(sr[budget_index(sr,fraction)],ratio),
                riskSameReviewBudget=add_cost(sr[budget_index(sr,.5)],ratio))
        result["comparisons"].append(comparison)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input",type=Path,default=ROOT/".local/triviaplus_dataset.parquet")
    parser.add_argument("--output",type=Path,default=ROOT/".local/triviaplus-review-report.json")
    args=parser.parse_args()
    if hashlib.sha256(args.input.read_bytes()).hexdigest()!=DATA_SHA:
        parser.error("Dataset differs from pinned TRIVIA+ release; recheck provenance before measuring")
    rows, excluded=rows_from_parquet(args.input)
    result=evaluate(rows)
    result["excludedInvalidRows"]=excluded
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k!="curve"},indent=2))


if __name__=="__main__":
    main()
