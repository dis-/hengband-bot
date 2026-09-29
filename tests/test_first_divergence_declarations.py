"""Pins for the record-only first-divergence declaration summary."""

import unittest

from first_divergence_s3_3 import _declaration_counts


class DeclarationSummaryTest(unittest.TestCase):
    def test_counts_mismatches_by_family_and_states_and_missing_decisions(self):
        acting = {"state": "acting"}
        calls = [
            ("x", "reason", 1, {}, {"owner": "home-visit",
                                     "execution": acting,
                                     "declaration_mismatch": {
                                         "inferred": "awaiting",
                                         "declared": acting}}),
            (None, "reason", 2, {}, {"owner": "calibration",
                                        "execution": None}),
            ("y", "reason", 3, {}, {"owner": "calibration",
                                     "execution": None}),
        ]
        counts = _declaration_counts(calls)
        self.assertEqual(counts["declaration_mismatch_counts"], [{
            "family": "home-visit", "inferred": "awaiting",
            "declared": "acting", "count": 1,
        }])
        self.assertEqual(counts["missing_declaration_decisions"], 2)
        self.assertEqual(counts["missing_declaration_by_family"],
                         {"calibration": 2})
        self.assertEqual(counts["declaration_decisions_measured"], 3)


if __name__ == "__main__":
    unittest.main()
