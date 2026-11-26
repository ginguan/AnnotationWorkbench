import unittest
from collections import Counter
from scripts.assign_citation_pilot import assign


class CitationAssignmentTests(unittest.TestCase):
    pairs = [{"pair": "p", "case_a": "a", "case_b": "b"},
             {"pair": "q", "case_a": "c", "case_b": "d"}]
    people = list("1234")

    def test_balances_both_case_and_position_and_is_reproducible(self):
        rows = assign(self.pairs, self.people, seed=24)
        self.assertEqual(rows, assign(self.pairs, self.people[::-1], seed=24))
        self.assertEqual(len(rows), 16)
        counts = Counter((r["case"], r["mode"], r["order"]) for r in rows)
        self.assertEqual(len(counts), 16)
        self.assertTrue(all(n == 1 for n in counts.values()))
        self.assertEqual(len({(r["reviewer"], r["case"]) for r in rows}), len(rows))

    def test_rejects_repeated_cases_or_reviewers(self):
        with self.assertRaises(ValueError):
            assign(self.pairs + [{"pair": "r", "case_a": "a", "case_b": "e"}], self.people)
        with self.assertRaises(ValueError):
            assign(self.pairs, ["1", "1"])
