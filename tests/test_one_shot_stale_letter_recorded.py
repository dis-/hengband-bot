"""A staged one-shot buy is sent only while its letter names its ware on the entry page.

Recorded: tests/fixtures/n1c-222-one-shot-stale-letter-20261124.jsonl.gz, n1-c life-222
(Magic-Eater Lv26), 2026-11-24 19:53, rows of snapshots-current from the incident capture
``20261124-195357-stuck-prompt``: the weapon store page at turn 858002 (19 wares, plain
crossbow bolts at ``p``), the outside board at turn 858011, and the re-entered page at turn
858011 (store maintenance ran on that entry: 15 wares, the same bolts at ``h``).  Live, the
staged ``pp6\r\r\x1b`` was sent on the 15-ware page and the purchase prompt stuck.

DECLARED: ``_skill_exp_request_key`` is off and Home is known (the ~f probe and the Home scan
have their own tests; this purchase reads neither).  CONSTRUCTED where a test says so.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

from dataclasses import replace
import gzip
import json
from pathlib import Path
import unittest

from hengbot.model import StoreState, parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import LEAVE_STORE_KEY

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-222-one-shot-stale-letter-20261124.jsonl.gz"


class OneShotStaleLetterRecorded(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream]
        cls.old_page = parse_snapshot(rows[1], {})
        cls.outside = parse_snapshot(rows[2], {})
        cls.new_page = parse_snapshot(rows[3], {})

    def policy(self):
        policy = HengbotPolicy()
        policy._skill_exp_request_key = lambda _snapshot: None
        policy._home_knowledge_current = True
        policy._equipment_catalog.home_scan_complete = True
        return policy

    def stage(self, policy):
        """Observe the 19-ware page and post the entry, as live (decisions 1874-1875)."""
        self.assertEqual(policy.choose_key(self.old_page), LEAVE_STORE_KEY)
        self.assertEqual(
            (policy.choose_key(self.outside), policy.last_reason),
            ("5", "shop:one-shot-buy"),
        )
        self.assertTrue(policy.confirm_key_posted("5"))
        self.assertEqual(policy._store_visit.operation_key[:2], "pp")

    def test_recorded_pages_hold_the_bolts_at_different_letters(self):
        def bolts(page):
            return [(w.letter, w.count) for w in page.store.items
                    if w.tval == 18 and w.to_h == 0 and w.to_d == 0]
        self.assertEqual((len(self.old_page.store.items), bolts(self.old_page)), (19, [("p", 81)]))
        self.assertEqual((len(self.new_page.store.items), bolts(self.new_page)), (15, [("h", 99)]))

    def test_reshuffled_entry_page_sends_no_stale_buy_and_recomposes_from_it(self):
        policy = self.policy()
        self.stage(policy)

        key = policy.choose_key(self.new_page)
        self.assertFalse(key.startswith("p"), key)
        self.assertEqual(key, LEAVE_STORE_KEY)
        self.assertEqual(policy._store_visit_last_closed.outcome, "one-shot-buy-stale-page")

        # The page the game showed is now the observation the next buy is composed from.
        outside = replace(self.outside, turn=self.new_page.turn + 1)
        self.assertEqual(policy.choose_key(outside), "5")
        self.assertTrue(policy.confirm_key_posted("5"))
        reentered = replace(self.new_page, turn=outside.turn)
        self.assertEqual(
            (policy.choose_key(reentered), policy.last_reason),
            ("ph6\r\r\x1b", "shop:one-shot-buy"),
        )

    def test_unchanged_entry_page_releases_the_staged_buy(self):
        policy = self.policy()
        self.stage(policy)
        same = replace(self.old_page, turn=self.new_page.turn)
        self.assertEqual(
            (policy.choose_key(same), policy.last_reason),
            ("pp6\r\r\x1b", "shop:one-shot-buy"),
        )
        self.assertTrue(policy._store_visit.operation_released)

    def test_other_ware_at_the_staged_letter_is_not_bought(self):
        """CONSTRUCTED: the re-entered page keeps 19 rows, but row ``p`` is another ware."""
        policy = self.policy()
        self.stage(policy)
        wares = list(self.old_page.store.items)
        index = next(i for i, w in enumerate(wares) if w.letter == "p")
        wares[index] = replace(wares[0], letter="p")
        swapped = replace(
            self.old_page,
            store=StoreState(self.old_page.store.store_type, wares),
            turn=self.new_page.turn,
        )
        key = policy.choose_key(swapped)
        self.assertFalse(key.startswith("p"), key)
        self.assertEqual(policy._store_visit_last_closed.outcome, "one-shot-buy-stale-page")


if __name__ == "__main__":
    unittest.main()
