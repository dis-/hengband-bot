"""A shop whose page composed nothing is not re-entered, and a caster's spare Identify staff sells
(n1-a life-545, MAINTAINABILITY.md 2 and 3).

Recorded (tests/extract_n1a_545_shop_uncomposable_1127_fixture.py, ``n1a-545-shop-uncomposable-1127``):
the town-arrival checkpoint of 2026-11-27 12:54:31 (Amberite Rogue CL34, Sorcery, 鑑定 usable).
Row 32 bought the General Store's six Hard Biscuits: its 91 Rations need a new pack slot and the
pack stood at the four-slot floor, so food stayed 6 of 7 Rations' worth (counted by nutrition,
food_supply).  Row 35's pack-headroom pass, started for that Ration, walked the 15-charge Identify
staff (of 16+15) to the Magic shop: the caster's carry cap releases it.  Row 36's in-store sale
refused it under the 20-charge reserve (2026-10-07), which binds only where the staff is the
identification, so the page composed nothing and the visit left; row 37 settled the shop as
observed-operation-uncomposable, and the same pass walked straight back in (rows 37-86, 17 times)
until town:blocked:stage-deadline:buy.

Every row before the one decided is replayed through the public ``choose_key`` and posts the
recorded key (full state through row 40; the CLI's owner retirement of row 41 is not journalled).

DECLARED CONSTRUCTED: ``PRE_FIX_RESERVE`` restores the old reserve rule (the in-store sale
applies the 20-charge reserve, the outside pass none) so the replay reaches the recorded loop.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from hengbot.policy_constants import STAFF_IDENTIFY_MIN_CHARGES
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-545-shop-uncomposable-1127"
GENERAL_STORE, MAGIC_SHOP, HOME = 0, 5, 7
FIRST_FOOD_TRAVEL = 31     # recorded: to the General Store
STAFF_SALE_TRAVEL = 35     # recorded: to the Magic shop
OBSERVED_PAGE = 36         # recorded: shop:observe-and-leave
RE_ENTRY = 37              # recorded: ('7', shop:observed-operation-uncomposable)
LOOP = ("7", "shop:observed-operation-uncomposable")
SPARE_STAFF = "r"


def _pre_fix_reserve(self, snapshot, item):
    if sys._getframe(1).f_code.co_filename.endswith("town_pack_headroom.py"):
        return False
    total = self._total_identify_staff_charges(snapshot)
    remaining = total - max(0, item.charges) * self._retention_surplus(snapshot, item)
    return total >= STAFF_IDENTIFY_MIN_CHARGES and remaining < STAFF_IDENTIFY_MIN_CHARGES


PRE_FIX_RESERVE = mock.patch.object(
    HengbotPolicy, "_identify_staff_release_breaks_reserve", _pre_fix_reserve)
NO_SETTLEMENT_GUARD = mock.patch.object(
    HengbotPolicy, "_store_observed_unavailable", lambda *args: False)


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


def decide(policy, board):
    with contextlib.redirect_stdout(io.StringIO()):
        key = policy.choose_key(board)
    return key, policy.last_reason


class ShopUncomposable545RecordedTest(unittest.TestCase):
    def replay(self, row):
        """The policy and board of ``row``, every earlier recorded row replayed and matched."""
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        policy, journal, steps = load(FIXTURE, Path(scratch.name), adopt_recorded_calibration=False)
        self.assertEqual((journal[RE_ENTRY]["key"], journal[RE_ENTRY]["reason"]), LOOP)
        for recorded, supply in steps[:row]:
            key, reason = decide(policy, supply())
            self.assertEqual((key, reason), (recorded["key"], recorded["reason"]), recorded["row"])
            post(policy, recorded["key"])
        return policy, steps[row][1](), journal[row]

    def test_the_spare_staff_of_a_caster_is_sold_first(self):
        policy, board, recorded = self.replay(FIRST_FOOD_TRAVEL)
        self.assertTrue(policy._identify_staff_replaced(board))
        sale = policy._find_device_sale(board)
        self.assertEqual((sale.slot, sale.charges), (SPARE_STAFF, 15))
        key, reason = decide(policy, board)
        self.assertEqual(reason, "shop:travel")
        self.assertNotEqual(key, recorded["key"])
        self.assertEqual(policy._shopping_approach_store_type, MAGIC_SHOP)

    def test_with_the_reserve_reverted_the_recorded_food_trip_returns(self):
        with PRE_FIX_RESERVE:
            policy, board, recorded = self.replay(FIRST_FOOD_TRAVEL)
            self.assertIsNone(policy._find_device_sale(board))
            self.assertEqual(decide(policy, board), (recorded["key"], recorded["reason"]))
        self.assertEqual(policy._shopping_approach_store_type, GENERAL_STORE)

    def test_the_observed_magic_shop_page_composes_the_sale(self):
        # CONSTRUCTED: the recorded rows to the Magic shop under the old rule, the page under the fix.
        with PRE_FIX_RESERVE:
            policy, board, recorded = self.replay(OBSERVED_PAGE)
        self.assertEqual(board.store.store_type, MAGIC_SHOP)
        self.assertEqual(recorded["reason"], "shop:observe-and-leave")
        key, reason = decide(policy, board)
        self.assertNotEqual(reason, "shop:observe-and-leave")
        self.assertEqual((key, reason), ("{" + SPARE_STAFF + "@0\r", "shop:in-store-inscribe"))

    def test_a_shop_settled_as_uncomposable_is_not_re_entered(self):
        with PRE_FIX_RESERVE:
            policy, board, recorded = self.replay(RE_ENTRY)
            key, reason = decide(policy, board)
        # This board settled the observed page (_resolve_observed_uncomposable_stop) ...
        self.assertIn(MAGIC_SHOP, policy._town_visit_ledger.nonhome_attempted_without_effect)
        self.assertEqual(policy._shop_selector_diagnostics["observed_stop_settlement"]["store_type"],
                         MAGIC_SHOP)
        # ... and the pass moves on to its Home deposit instead of walking back in.
        self.assertNotEqual((key, reason), LOOP)
        self.assertEqual(reason, "shop:travel")
        self.assertEqual(policy._shopping_approach_store_type, HOME)
        self.assertEqual(policy._shop_selector_diagnostics["observed_unavailable"], {
            "store_type": MAGIC_SHOP, "requester": "shop-sell",
            "reason": "observed-operation-uncomposable",
            "decision_sequence": policy._decision_sequence})

    def test_without_the_settlement_guard_the_recorded_loop_returns(self):
        with PRE_FIX_RESERVE, NO_SETTLEMENT_GUARD:
            policy, board, recorded = self.replay(RE_ENTRY)
            self.assertEqual(decide(policy, board), LOOP)


if __name__ == "__main__":
    unittest.main()
