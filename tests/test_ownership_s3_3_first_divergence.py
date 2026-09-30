"""Frozen #8 trajectory expectations, set before correcting the ON policy.

These are continuous-replay first differences.  Later focus boards in the
design are isolated scenarios, never evidence that an amended path reached
them.  An earlier measured difference is a defect, not a new expectation.
"""

import unittest

import tests  # noqa: F401  (bare runs stay isolated from runtime files)


# List indices, distinct from decision_sequence.  The tour's declared
# KNOWN_HARNESS_DIVERGENCES index 2701 is an OFF/historical wall difference;
# Ruling 2026-09-29 #2, design #8 §1: the open router Reach continues
# after its posted travel releases, so the tour row is index 2703.
EXPECTED_FIRST = {
    # Ruling 2026-09-30 #7: the store-4 one-shot purchase (2044) released and no entry
    # is posted, so the OFF entry wait has no live identity (ruling #1); the plan's
    # next stop is store 3 (「実行順は予定表」, ruling #5 review item 7).
    "tour": (2048, 2046, "`n(.", "shop:travel"),
    # Ruling 2026-09-29 #4 (supersedes #2 for this row), design #8 section 3
    # 'ready child/action executes': the posted `dm` deposit's effect is
    # observed on this board (s3-town-1179-live2.md), so the session's next
    # planned deposit (pack:055751ff10eb08e9, slot l) is dispatched.
    "town": (1179, 1177, "dl", "equipment-transaction:deposit"),
    "overweight": (3724, 3723, "3", "shop:approach"),
    # Ruling #5 review item 7: after the Home operation releases, the plan's
    # next stop is store 3 (shop-buy). The free-standing enchant rung yields
    # to the router for that stop on recorded decision 20.
    "withdraw": (20, 20, "\x1b`n%.", "shop:travel"),
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
            "tour": (2048, 2046, "`n(.", "shop:travel"),
            "town": (1179, 1177, "dl", "equipment-transaction:deposit"),
            "overweight": (3724, 3723, "3", "shop:approach"),
            "withdraw": (20, 20, "\x1b`n%.", "shop:travel"),
            "recall": None, "stuck": None,
        })

    def test_early_difference_is_a_defect_not_an_accepted_row(self):
        self.assertEqual(trajectory_defect("tour", {
            "list_index": 2000, "historical_sequence": 1998,
            "on": ["5", "ownership:holder-complete"],
        }), "early-divergence")
        self.assertEqual(trajectory_defect("withdraw", {
            "list_index": 3, "historical_sequence": 3,
            "on": ["5", "ownership:holder-complete"],
        }), "early-divergence")

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
