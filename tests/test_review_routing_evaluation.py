import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evaluate_review_routing import curves, features, partition_reviews, review_sequence, choose_budget


class ReviewRoutingTest(unittest.TestCase):
    def test_review_roles_are_reproducible_and_disjoint(self):
        roles = partition_reviews(4, "case")
        self.assertEqual(roles, partition_reviews(4, "case"))
        self.assertEqual(sorted(roles), list(range(4)))
        with self.assertRaises(ValueError):
            partition_reviews(1, "case")

    def test_risk_selection_includes_audit_and_spends_one_slot_per_item(self):
        n = 25
        order = review_sequence(n, 11, list(reversed(range(n))))
        self.assertEqual(order[:9], list(range(9)))
        self.assertEqual(set(order), set(range(n)))
        self.assertEqual(len(order), n)
        self.assertEqual(order, review_sequence(n, 11, list(reversed(range(n)))))

    def test_replay_counts_flagged_and_corrected_separately(self):
        rows = [
            {"second":1,"reference":1,"independent":0},
            {"second":1,"reference":0,"independent":1},
            {"second":0,"reference":1,"independent":1},
        ]
        seq = curves(rows, [1,0,-1])
        self.assertEqual((seq[0]["missed"], seq[0]["recovered"]), (2,0))
        self.assertEqual((seq[2]["adjudications"], seq[2]["recovered"], seq[2]["missed"]), (2,1,1))
        self.assertEqual(curves(rows,[1,0,-1],reference="independent")[1]["recovered"],0)
        self.assertEqual(choose_budget(seq,{"recovered":1},2), 1)

    def test_features_do_not_accept_outcomes(self):
        x = features("Unopened items can be returned in 30 days.", "What is the policy?",
                     "Items are returnable after 90 days.", "ms_marco", "model", ["supports"])
        self.assertEqual(x["unseen_number_fraction"], 1)
        self.assertEqual(x["source"], "msmarco")
        self.assertFalse({"second", "reference", "workerId", "rater_count"} & x.keys())


if __name__=="__main__":
    unittest.main()
