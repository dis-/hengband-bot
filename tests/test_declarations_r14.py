"""Recorded Home-tail continuation after a posted Home exit."""

import unittest

import tests  # noqa: F401 -- isolate runtime files
from scripts.first_divergence_s3_3 import measure


class DeclarationR14Test(unittest.TestCase):
    def test_overweight_home_tail_keeps_its_operation_at_3715(self):
        # The OFF replay identifies a device here.  With S3.3 enabled the
        # Home operation is still open and its exit continuation owns the row.
        row = measure("overweight", "s33")["first_divergence"]
        self.assertEqual((row["list_index"], row["historical_sequence"]),
                         (3715, 3714))
        self.assertEqual(row["off"], ["rjp", "identify:device"])
        self.assertEqual(row["on"], ["\x1b", "home:leave-after-one-operation"])
        before = row["pre_decision_on"]
        self.assertEqual(before["parent"]["family"], "home-visit")
        self.assertEqual(before["operation"]["identity"],
                         (7, 3711, "de1\r\x1b"))
        self.assertTrue(any(
            delegate["delegate_family"] == "home-tail"
            and delegate["lifecycle"] == "open"
            and delegate["parent_claim_id"] == before["parent"]["claim_id"]
            for delegate in before["delegates"]
        ))


if __name__ == "__main__":
    unittest.main()
