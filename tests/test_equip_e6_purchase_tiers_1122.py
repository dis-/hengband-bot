"""Equipment review E6, owner Q8: the shopping table's rows carry a tier.

Owner 2026-11-22 (verbatim): 「買い物の表の段に最優先・必須・任意の区分を付け、お金が足りない時は区分の
高い段から買う。今の順は区分の中で保つ」.  purchase_rungs ``PURCHASE_RUNG_TIER`` gives every rung of
HengbotPolicy._purchase_rungs its tier; ``short_money_choice`` picks, among today's picks in today's
order, the first one with the gold for all of them and the first of the highest tier without it.
The shop's selector (``_tiered_purchase``) and the departure's required buy on a page
(``_departure_blocking_page_purchase_pure``) both read it.

Recorded: n1-a life-531's town visit of 2026-11-19 (tests/fixtures/n1a-531-q33-scrolls-1119, the
Q33 scrolls stop; every row decided through choose_key and acknowledged as recorded).  Row 92 is
the Black Market's page with 98,308 gold: today's order (the legacy selector) picks the
*鑑定*の巻物 (4 x 9,555 gold, rung identify:full, 必須) before the *破壊*の杖 (3回分) (62,114 gold,
rung black-market:destruction, 最優先); the two cost 100,334, so the gold is short.  Live the page
bought the staff (``pV``) through the priority errand (bm_destruction_fund.page_purchase); the tier
rule (``_tiered_purchase``, read on today's own picks) chooses it as well.

DECLARED CONSTRUCTED: the same page with 200,000 gold (enough for both): today's order stands.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

from hengbot import me_staff_sequence, purchase_rungs, zul_trip
from hengbot.policy import staged_prompt_chain_matches
from hengbot.model import RESTORE_POTION_SVAL_BY_STAT
from hengbot.purchase_rungs import (
    TIER_OPTIONAL, TIER_PRIORITY, TIER_REQUIRED, TIERS, PurchaseContext,
    purchase_rung_tier, short_money_choice,
)
from support.town_arrival_fixture import load
from tests.test_destroy_procurement_guard import active_detection_fixture

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-531-q33-scrolls-1119"
PAGE_ROW = 92


class TierTableTest(unittest.TestCase):
    def test_every_live_rung_declares_its_tier(self):
        policy, snapshot, _ = active_detection_fixture()
        snapshot = replace(snapshot, player=replace(
            snapshot.player, drained_stats=tuple(RESTORE_POTION_SVAL_BY_STAT)))
        with mock.patch.object(type(policy), "_carry_procurement_strategy",
                               return_value=SimpleNamespace(required_force={})):
            rungs = policy._purchase_rungs(PurchaseContext(snapshot))
        self.assertGreater(len(rungs), 40)
        self.assertEqual([rung.rung_id for rung in rungs if rung.tier not in TIERS], [])
        for rung in rungs:
            self.assertEqual(rung.tier, purchase_rung_tier(rung.rung_id), rung.rung_id)
        # The exclusive shopping lists (opening Q1 rows are ordinary ids above).
        for rung_id in (zul_trip.BUY_RUNG, me_staff_sequence.BUY_RUNG):
            self.assertIn(purchase_rung_tier(rung_id), TIERS, rung_id)

    def test_the_owner_s_first_priority_rows(self):
        priority = sorted(rung for rung, tier in purchase_rungs.PURCHASE_RUNG_TIER.items()
                          if tier == TIER_PRIORITY)
        self.assertEqual(priority, ["black-market:destruction", "priority-ware:rocket",
                                    "priority-ware:speed-staff", "priority-ware:telepathy"])
        for rung in ("mandatory:recall", "mandatory:food", "mandatory:teleport", "mandatory:cure",
                     "mandatory:destruction", "ability-gear:buy", "restore:str"):
            self.assertEqual(purchase_rung_tier(rung), TIER_REQUIRED, rung)
        for rung in ("tail:heroism", "tail:ammo", "black-market:speed", "me-device:policy"):
            self.assertEqual(purchase_rung_tier(rung), TIER_OPTIONAL, rung)
        self.assertIsNone(purchase_rung_tier("tail:new-purchase"))

    def test_short_money_buys_the_highest_tier_first_keeping_the_order_within_it(self):
        picks = [("torch", 100, TIER_OPTIONAL), ("teleport", 300, TIER_REQUIRED),
                 ("cure", 200, TIER_REQUIRED), ("rocket", 400, TIER_PRIORITY)]
        self.assertEqual(short_money_choice(picks, 1000), "torch")      # the gold covers all
        self.assertEqual(short_money_choice(picks, 999), "rocket")      # short: 最優先
        self.assertEqual(short_money_choice(picks[:3], 599), "teleport")  # 必須, today's order
        self.assertEqual(short_money_choice(picks[:1], 50), "torch")
        self.assertIsNone(short_money_choice([], 100))


class TieredSelectorRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, _journal, steps = load(FIXTURE, Path(cls.scratch.name))
        for recorded, supply in steps[:PAGE_ROW]:
            board = supply()
            with contextlib.redirect_stdout(io.StringIO()):
                policy.choose_key(board)
            if recorded["key"]:
                policy.confirm_key_posted(recorded["key"])
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, recorded["key"]):
                    policy.commit_staged_prompt_chain(
                        {"outcome": "released", "posted": recorded["key"]})
        cls.recorded, supply = steps[PAGE_ROW]
        cls.page = supply()
        cls.policy = policy

    @classmethod
    def tearDownClass(cls):
        cls.policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def ware(self, letter):
        return next(item for item in self.page.store.items if item.letter == letter)

    def today(self, board):
        return self.policy._legacy_next_purchase_unreserved(board, commit_state=False)

    def test_today_s_order_puts_the_required_scroll_before_the_priority_staff(self):
        policy, page = self.policy, self.page
        scroll, staff = self.ware("u"), self.ware("V")
        self.assertTrue(self.recorded["key"].startswith("pV"))
        self.assertEqual(page.player.gold, 98308)
        self.assertEqual(self.today(page), scroll)
        self.assertEqual(policy._purchase_tier(page, scroll), TIER_REQUIRED)
        self.assertEqual(policy._purchase_tier(page, staff), TIER_PRIORITY)
        self.assertGreater(policy._purchase_cost(page, scroll) + policy._purchase_cost(page, staff),
                           page.player.gold)

    def test_short_of_gold_the_priority_staff_goes_first(self):
        policy, page = self.policy, self.page
        chosen = policy._tiered_purchase(page, self.today(page), set(), False)
        self.assertEqual(chosen, self.ware("V"))
        self.assertEqual(policy._shop_selector_diagnostics["purchase_tier"],
                         "short-money:required->priority")

    def test_with_the_gold_for_both_today_s_order_stands(self):
        policy = self.policy
        rich = replace(self.page, player=replace(self.page.player, gold=200000))
        first = self.today(rich)
        self.assertEqual(first, self.ware("u"))
        self.assertEqual(policy._tiered_purchase(rich, first, set(), False), first)


if __name__ == "__main__":
    unittest.main()
