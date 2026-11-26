import random
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from prepare_blind_audit import prepare

def cases():
    return [{"id": str(i), "skipped": i < 205, "question": "What?",
             "answer": "Something", "passages": ["A harmless test passage."],
             "first_label": "hidden", "risk_score": .12} for i in range(270)]

class BlindAuditTest(unittest.TestCase):
    def test_mixed_packet_strips_routing_and_expected_label(self):
        packet, record = prepare(cases(), .05, 10, random.Random(2))
        self.assertEqual(len(packet), 58)
        self.assertTrue(all(set(row) == {"blind_id", "question", "answer", "passages"}
                            for row in packet))
        self.assertEqual(sum(r["skipped"] for r in record["key"].values()), 48)
        self.assertEqual(len({r["case_id"] for r in record["key"].values()}), 58)
        self.assertEqual({r["blind_id"] for r in packet}, set(record["key"]))

    def test_invalid_batch_cannot_pass_silently(self):
        rows = cases()
        for batch, controls in [(rows + [rows[1]], 10), (rows, 66), (rows, 0)]:
            with self.assertRaises(ValueError):
                prepare(batch, .05, controls)
