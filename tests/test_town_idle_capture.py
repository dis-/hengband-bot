"""Issue #47: a refused Home route must release its request and yield."""
import tests  # noqa: F401

import unittest

from tests.town_idle_capture_replay import replay_idle
from tests.town_s2_exit_replay import replay_n1


class TownIdleCaptureTest(unittest.TestCase):
    def check_capture(self, stamp, turn):
        replay = replay_idle(stamp)
        self.assertEqual(replay["scan"], "~9\x1b\x1b")
        first = replay["trace"][0]
        self.assertEqual(first["turn"], turn)
        self.assertEqual((first["key"], first["reason"]),
                         ("5", "town:blocked:no-actionable-claim-owner"))
        withdrawal = next(row for row in first["admissions"]
                          if row["terminal"][0] == "home-withdraw")
        self.assertEqual(withdrawal["codes"], ["reservation-unavailable"])
        self.assertEqual(withdrawal["closed"],
                         "terminal-refused-unserved:reservation-unavailable")
        self.assertNotIn("legacy-withdrawal", first["request"])
        following = replay["trace"][1]
        self.assertEqual((following["key"], following["reason"]),
                         ("1", "shop:approach"))
        for step in replay["trace"]:
            self.assertNotEqual(step["reason"], "policy:none-wait")
            for row in step["admissions"]:
                self.assertTrue(row["closed"] or row["live"], row)

    def test_first_capture(self):
        self.check_capture("095121", 584559)

    def test_second_capture(self):
        self.check_capture("100744", 699921)

    def test_admitted_route_keeps_its_none_continuation(self):
        trace = replay_n1("20261018-091516")
        expected = next(row for row in trace if row["turn"] == 1062666)
        self.assertEqual((expected["key"], expected["reason"]), ("5", "policy:none-wait"))
        self.assertFalse(any(row["terminal"][0] == "home-withdraw"
                             for row in expected["admissions"]))
