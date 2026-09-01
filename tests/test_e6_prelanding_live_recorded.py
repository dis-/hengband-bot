from __future__ import annotations

from collections import Counter
import unittest

import e6_prelanding_live_recorded as recorded
from historical_emit_fixture import E6_PRELANDING_DECISIONS, rows


class E6PrelandingLiveRecordedTest(unittest.TestCase):
    def test_post_cutoff_population_pins_reachable_outcomes(self):
        report = recorded.measure(list(rows(E6_PRELANDING_DECISIONS)))
        self.assertEqual((3490, 35, 11), (
            report["rows"], report["shop_one_shot_rows"], report["creations"],
        ))
        self.assertEqual(11, report["same_store_posted_leaving_predecessors"])
        self.assertEqual(11, report["provable_granted_new"])
        self.assertEqual(111, report["acquire_calls"])
        self.assertEqual(Counter({"granted-new": 77, "granted-existing": 34}),
                         report["acquire_results"])
        self.assertEqual(0, report["acquire_results"]["refused"])


if __name__ == "__main__":
    unittest.main()
