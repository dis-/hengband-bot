"""Recorded live35 board/screen pins at the production procurement seam.

The captured checkpoint is after the bad key. Rebuild only the pre-decision
Home exit reason on the recorded input board, without mocking producers.
"""
import tests  # noqa: F401
import hashlib
import json
from pathlib import Path
import unittest

from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy


class Live35StorePageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = (Path(__file__).parent / "fixtures" / "live35-store-page.json").read_bytes()
        if hashlib.sha256(raw).hexdigest() != (
                "fcf4829790ce4982bc6fdc77cca3bac4a664470be415bad08757cb8ed84ccb43"):
            raise AssertionError("live35 recorded fixture changed")
        cls.capture = json.loads(raw)

    def case(self, index=1):
        board = parse_snapshot(self.capture["boards"][index])
        policy = HengbotPolicy()
        policy.prime(board)
        return policy, board

    def test_recorded_screen_and_posted_keys_explain_the_chooser(self):
        decisions = {r["decision_sequence"]: r for r in self.capture["decisions"]}
        self.assertEqual(decisions[2674]["key"], "Eg")
        self.assertEqual(decisions[2675]["key"], "~9\x1b")
        self.assertEqual("".join(r["character"] for r in self.capture["posted"]
                                 if r["decision"]["sequence"] == 2674), "Eg")
        screen = self.capture["screen"]
        self.assertIn("どのアイテムを取りますか", "\n".join(screen["lines"]))
        policy, board = self.case()
        self.assertEqual(board.store.store_type, 7)
        self.assertEqual(policy._find_edible(board).slot, "g")

    def test_recorded_home_scan_exit_survives_production_arbitration(self):
        policy, board = self.case()
        policy.last_reason = "home:scan-incomplete-open-page"
        policy._offer_execution(
            "\x1b", producer="home-scan", work_id="recorded-home-exit",
            next_step="store.leave.send", expected_effect="outside-store",
        )
        self.assertEqual(policy._town_procurement_decision(board, "\x1b"), "\x1b")
        self.assertEqual(policy.last_reason, "home:scan-incomplete-open-page")

    def test_store_language_is_preserved_for_all_exit_and_wait_owners(self):
        for index in (1, 2):
            for reason in ("home:scan-incomplete-open-page", "shop:observe-and-leave",
                           "survival:eat", "emergency:heal", "rest", "town:recover",
                           "no-wait:escape-scroll"):
                for key in ("\x1b", "\r"):
                    with self.subTest(index=index, reason=reason, key=key):
                        policy, board = self.case(index)
                        policy.last_reason = reason
                        self.assertEqual(policy._town_procurement_decision(board, key), key)
                        self.assertEqual(policy.last_reason, reason)


if __name__ == "__main__":
    unittest.main()
