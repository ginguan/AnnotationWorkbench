import unittest
from scripts.load_citation_pilot import packet, seeded_reviews
from scripts.assign_citation_pilot import assign


class CitationFixtureTests(unittest.TestCase):
    def test_every_case_is_matched_and_both_review_spans_are_valid(self):
        rows, references, manifest = packet()
        self.assertEqual(set(references), {row["id"] for row in rows})
        self.assertEqual(len(assign(manifest, ["r1", "r2", "r3", "r4"])), 32)
        self.assertEqual(list(references.values()).count("supported"), 4)
        for index, row in enumerate(rows):
            first, second = seeded_reviews(index, row)
            self.assertNotEqual(first["verdict"], second["verdict"])
            self.assertNotIn("reference", row)
            for review in (first, second):
                for span in review["spans"]:
                    encoded = row[span["target"]].encode("utf-16-le")
                    self.assertGreater(span["end"], span["start"])
                    self.assertLessEqual(span["end"] * 2, len(encoded))
