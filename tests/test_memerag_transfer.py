import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evaluate_memerag_transfer import evaluation_rows

def item(q, left):
    support, miss = "Supported", "Not Supported"
    return {"query_id": q, "query": "Query", "context": [{"text": "supporting context"}],
            "answer": [{"sentence": "One", "factuality": [left,support,miss,miss,support]},
                       {"sentence": "Two", "factuality": [support,miss,support,support,support]}]}

class TransferTest(unittest.TestCase):
    def test_question_aggregates_sentences_without_exposing_reserved_votes_as_features(self):
        rows = evaluation_rows([item(1, "Supported"),item(2, "Not Supported")])
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["reference"], rows[0]["second"]), (1,1))
        self.assertEqual(rows[0]["features"]["first_sentence_count"], 2)
        self.assertNotIn("first_supplementary_fraction", rows[0]["features"])

    def test_duplicate_question_is_rejected(self):
        row = item(1, "Supported")
        with self.assertRaises(ValueError):
            evaluation_rows([row,row])
