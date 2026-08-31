from __future__ import annotations

import unittest

from town_acquire_bypass_recorded import controls, measure


class TownAcquireBypassRecordedTest(unittest.TestCase):
    def _decision(self, sequence, key="5", *, opened=1, approach=None):
        return {
            "time": f"2026-08-31T12:00:0{sequence}", "turn": 10 + sequence,
            "decision_sequence": sequence, "key": key, "reason": "shop:approach",
            "position": {"y": 1, "x": 1}, "store_type": None,
            "shopping_approach_store_type": approach,
            "store_visit": {"owner": "town-errand", "store_type": 3,
                            "opened_sequence": opened, "phase": "approaching"},
        }

    def _ledger(self, sequence, key="5"):
        return {"time": f"2026-08-31T12:00:0{sequence}", "posted_key": key,
                "line_turns": [10 + sequence]}

    def test_reverse_join_proxy_target_and_controls_use_wrong_values(self):
        decisions = [self._decision(1, opened=1), self._decision(2, opened=1)]
        ledger = [self._ledger(1), self._ledger(2),
                  {"time": "2026-08-31T12:00:01.500", "posted_key": "\x1b", "line_turns": [99]}]
        result = measure(decisions, ledger)
        totals = result["totals"]
        self.assertEqual(1, totals["ledger_posts_without_decision"])
        self.assertEqual(1, totals["ledger_posts_without_decision_while_visit_open"])
        self.assertEqual(1, totals["non_opener_posts_proxy"])
        self.assertEqual(0, totals["non_opener_target_derivable"])
        self.assertEqual(("store-router", "town-errand", "approaching"), result["non_openers"][0]["group"])

        moved = controls(decisions, ledger, result)
        self.assertEqual((1, 2), moved["reverse_join"])
        self.assertEqual((1, 0), moved["non_opener_proxy"])
        self.assertEqual((0, 1), moved["derivable_target"])


if __name__ == "__main__":
    unittest.main()
