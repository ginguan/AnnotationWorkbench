"""Compare interval sweep against a small, exhaustive per-position oracle."""
from fractions import Fraction
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from triage import answer_iou, ordering

rng = random.Random(724)
for _ in range(1500):
    a, b = [[{"target": rng.choice(("answer","passages")), "start": i, "end": j}
             for i,j in (sorted(rng.sample(range(21),2)) for _ in range(rng.randrange(9)))]
            for _ in range(2)]
    x, y = [{i for row in side if row["target"]=="answer" for i in range(row["start"],row["end"])}
            for side in (a,b)]
    expected = Fraction(len(x&y),len(x|y)) if x|y else None
    assert answer_iou(a,b) == expected
    assert answer_iou(b,a) == expected

items = [{"state":"needs_adjudication","reason":reason,"overlap_exact":overlap}
         for reason,overlap in [("claim_span_split",Fraction(2,3)),("both_uncertain",None),
                                ("claim_span_split",Fraction(0,1)),("verdict_split",None),
                                ("claim_span_split",Fraction(1,3))]]
assert [ordering(row)[0] for row in sorted(items,key=ordering)] == [0,1,2,3,3]
assert sorted(items,key=ordering)[-2]["overlap_exact"] == Fraction(1,3)
print("PASS: 1,500 interval overlap cases match the per-position oracle; stable triage priorities.")
