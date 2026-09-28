"""Frozen #8 trajectory expectations, set before correcting the ON policy.

These are continuous-replay first differences.  Later focus boards in the
design are isolated scenarios, never evidence that an amended path reached
them.  An earlier measured difference is a defect, not a new expectation.
"""

import unittest


# List indices, distinct from decision_sequence.  The tour's declared
# KNOWN_HARNESS_DIVERGENCES index 2701 is an OFF/historical wall difference;
# Ruling 2026-09-29 #2, design #8 §1: the open router Reach continues
# after its posted travel releases, so the tour row is index 2703.
EXPECTED_FIRST = {
    "tour": (2703, 2701, "7", "shop:approach"),
    # Ruling 2026-09-29 #2, design #8 §3: the Home page command boundary
    # sends CR for the equipment deposit continuation.
    "town": (1179, 1177, "\r", "equipment-transaction:atomic-deposit"),
    "overweight": (3724, 3723, "3", "shop:approach"),
    "withdraw": None,
    "recall": None,
    "stuck": None,
}


def trajectory_defect(case, measured):
    """Classify the first difference without accepting an earlier row."""
    expected = EXPECTED_FIRST[case]
    if expected is None:
        return None if measured is None else "unexpected-divergence"
    if measured is None:
        return "missing-designed-divergence"
    index, historical_sequence, key, reason = expected
    if measured["list_index"] < index:
        return "early-divergence"
    if measured["list_index"] > index:
        return "missed-designed-row"
    if (measured["historical_sequence"], *measured["on"]) != (
        historical_sequence, key, reason
    ):
        return "wrong-designed-result"
    return None


class FirstDivergenceExpectationTest(unittest.TestCase):
    def test_expected_rows_are_fixed_by_design(self):
        self.assertEqual(EXPECTED_FIRST, {
            "tour": (2703, 2701, "7", "shop:approach"),
            "town": (1179, 1177, "\r", "equipment-transaction:atomic-deposit"),
            "overweight": (3724, 3723, "3", "shop:approach"),
            "withdraw": None, "recall": None, "stuck": None,
        })

    def test_early_difference_is_a_defect_not_an_accepted_row(self):
        self.assertEqual(trajectory_defect("tour", {
            "list_index": 2658, "historical_sequence": 2654,
            "on": ["5", "ownership:holder-complete"],
        }), "early-divergence")
        self.assertEqual(trajectory_defect("withdraw", {
            "list_index": 3, "historical_sequence": 3,
            "on": ["5", "ownership:holder-complete"],
        }), "unexpected-divergence")

    def test_only_exact_designed_result_passes(self):
        for case, expected in EXPECTED_FIRST.items():
            if expected is None:
                self.assertIsNone(trajectory_defect(case, None))
                continue
            index, historical_sequence, key, reason = expected
            row = {"list_index": index,
                   "historical_sequence": historical_sequence,
                   "on": [key, reason]}
            self.assertIsNone(trajectory_defect(case, row))
            row["on"] = [key, reason + ":changed"]
            self.assertEqual(trajectory_defect(case, row),
                             "wrong-designed-result")
