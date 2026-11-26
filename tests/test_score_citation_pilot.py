import unittest
from scripts.score_citation_pilot import score


def row(mode, case, order, active, rework=0, correct=1, pair="p1"):
    return dict(reviewer="r1", pair=pair, mode=mode, case=case, order=order,
                active_s=active, rework_s=rework, correct=str(correct))


class PilotScoreTests(unittest.TestCase):
    def test_reports_rework_and_errors_with_savings(self):
        result = score([
            row("baseline", "a", 1, 100),
            row("jump", "b", 2, 50, 30, 0),
            row("jump", "c", 1, 70, pair="p2"),
            row("baseline", "d", 2, 80, pair="p2"),
        ])
        self.assertEqual(result["mean_paired_seconds_saved_including_rework"], 15)
        self.assertEqual(result["jump_first_pairs"], 1)
        self.assertEqual(result["material_errors"], {"baseline": 0, "jump": 1})

    def test_rejects_repeat_and_incomplete_pairs(self):
        baseline = row("baseline", "a", 1, 100)
        with self.assertRaises(ValueError):
            score([baseline, row("jump", "a", 2, 40)])
        with self.assertRaises(ValueError):
            score([baseline])

    def test_rejects_non_finite_times_and_same_position(self):
        baseline = row("baseline", "a", 1, 100)
        with self.assertRaises(ValueError):
            score([baseline, row("jump", "b", 2, float("inf"))])
        with self.assertRaises(ValueError):
            score([baseline, row("jump", "b", 1, 40)])
