import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evaluate_review_priority import completed_by, compare

class ReviewPriorityTest(unittest.TestCase):
    def test_disagreement_requires_adjudication_before_counting_as_resolved(self):
        rows=[{"second":1,"reference":1},{"second":0,"reference":1}]
        self.assertEqual(completed_by(rows,[0,1],5),{"reviews":0,"resolved":0,"adjudications":0})
        self.assertEqual(completed_by(rows,[0,1],6),{"reviews":1,"resolved":1,"adjudications":1})
        self.assertEqual(completed_by(rows,[0,1],8),{"reviews":2,"resolved":1,"adjudications":1})

    def test_full_queue_keeps_same_quality(self):
        rows=[{"second":1,"reference":1},{"second":0,"reference":1}]
        results=compare(rows,[.1,.9])
        for report in results:
            self.assertEqual(report["random_order"],report["priority_order"])
