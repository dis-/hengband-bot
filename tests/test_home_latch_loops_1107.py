"""Home entrance ping-pong from a latch Home cannot serve (n1-c 2026-11-06).

DECLARED CONSTRUCTED boards in the shape of two recorded stops (the incident
captures stay on the viewing server; the town-arrival replays of both were
read for this fix):

- n1-c life-157 23:38-23:40 (bot-2540cceb8): on the Home page the digger
  latch queued the stored shovel (home:queue-digging-tool-withdraw); at the
  entrance the filed catalogue errand's cloak was composed first, and its post
  cleared the shared ``_home_withdrawal_queued``.  Item processing then read
  the queued shovel's absence from the pack as a failed withdrawal and
  deferred it (town-item-processing-missing-pending) while the digger latch
  held: the early Home return of ``_next_required_store_type`` ignored the
  stay's Home bounds and every Home page closed as
  home:route-claim-unfulfilled -- 244 entries, 30 passes of a bound of 3.
- n1-c life-153 20:35 (bot-cbdf723f5): the catalogue errand's sword was filed
  while the pack had room; with 19 items carried the town pack budget refused
  it, but the outside composer still selected it ahead of the queued crossbow
  bolts (which stack with the carried ones), returned nothing, and the Home
  page handed the refused take off again (home:leave-for-pending-withdraw ->
  town:blocked:repetition -> shop:travel:await-entry).
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs

import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from policy_fixtures import item, store_item
from hengbot.cli import _dispatch_response_lines
from hengbot.home_errand import HomeErrandRequest
from hengbot.model import STORE_HOME, TVAL_POTION, StoreState
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import HOME_KNOWLEDGE_MACRO
from tests.test_home_withdraw_moved_address import (
    BESIDE, BOLTS, LATER, PAGE_SIZE, board, carried, carried_bolts, wares,
)

CLOAK = SWORD = 3
# Valuable, distinct potions: nothing a town owner disposes of or merges.
FILLER_SVALS = (36, 37, 38, 39, 41, 59, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 29, 60)


def shelf_with(index, ware, **wares_args):
    shelf = list(wares(**wares_args))
    shelf[index] = ware
    return tuple(shelf)


def respond(policy, shelf):
    """Deliver the ``~9`` answer the posted knowledge request asked for."""
    response = {"type": "knowledge", "knowledge": {
        "category": "home", "menu_key": "9", "items": [
            {"slot": i, "name": ware.name, "tval": ware.tval, "sval": ware.sval,
             "count": ware.count, "is_equipment": ware.is_equipment, "known": True}
            for i, ware in enumerate(shelf)]}}
    with TemporaryDirectory() as directory:
        _dispatch_response_lines(
            [json.dumps(response)], policy, lambda _key: True,
            knowledge_ledger_path=Path(directory) / "response.jsonl")


def policy_for(shelf, pack=()):
    policy = HengbotPolicy()
    policy.prime(board(pack, turn=100, at=BESIDE))
    policy.consume_home_knowledge(shelf)
    policy._home_page_size = PAGE_SIZE
    return policy


def nineteen_item_pack(count=19):
    """A pack the town budget refuses a new slot (23 - 19 - 1 < 4)."""
    filler = [item(chr(ord("a") + i), TVAL_POTION, sval, name=f"potion {sval}")
              for i, sval in enumerate(FILLER_SVALS[:count - 1])]
    return [*filler, carried_bolts(20, slot=chr(ord("a") + count - 1))]


class QueuedDiggerBehindErrandTakeTest(unittest.TestCase):
    """life-157: another owner's take does not end the queued shovel."""

    def test_errand_take_posted_first_leaves_the_queued_shovel_queued(self):
        cloak = store_item("c", 35, 1, name="plain cloak [1,+0]", is_equipment=True)
        shelf = shelf_with(CLOAK, cloak)
        policy = policy_for(shelf)
        shovel = policy._item_signature(shelf[LATER])
        # As on the Home page (decision 19): the digger latch queued the shovel.
        policy._home_pending_item = shovel
        policy._home_digger_withdraw_pending = True
        policy._home_withdrawal_queued = True
        self.assertTrue(policy._file_home_errand(
            board(turn=101), HomeErrandRequest(
                policy._item_signature(cloak), 1, "home-catalog", "identification-catalog"),
            knowledge_current=True))
        policy._shopping_approach_store_type = STORE_HOME

        key = policy.choose_key(board(turn=102))
        self.assertEqual((key, policy.last_reason),
                         ("5pd\x1b", "home-errand:atomic-withdraw:identification-catalog"))
        policy.confirm_key_posted(key)
        pack = [carried(cloak, 1)]
        key = policy.choose_key(board(pack, turn=110))

        # Recorded: the shovel deferred and Home re-entered ('5').
        self.assertNotIn(shovel, policy._deferred_home_items)
        self.assertEqual(policy._home_pending_item, shovel)
        self.assertTrue(policy._home_withdrawal_queued)
        self.assertEqual((key, policy.last_reason),
                         (HOME_KNOWLEDGE_MACRO, "home:request-knowledge-scan"))
        policy.confirm_key_posted(key)
        policy.choose_key(board(pack, turn=111))
        respond(policy, tuple(ware for index, ware in enumerate(shelf) if index != CLOAK))
        key = policy.choose_key(board(pack, turn=112))
        self.assertEqual((key, policy.last_reason), ("5 pc1\r\x1b", "home:atomic-withdraw"))
        self.assertEqual(policy._home_atomic_withdraw_telemetry["selected_signature"],
                         list(shovel))


class UnservableHomeLatchTest(unittest.TestCase):
    """life-157: a latch Home cannot serve does not route Home again."""

    def deferred_shovel_policy(self):
        shelf = wares()
        policy = policy_for(shelf)
        shovel = policy._item_signature(shelf[LATER])
        # As after decision 21: the only stored digger deferred, the latch held.
        policy._defer_home_item(shovel, "town-item-processing-missing-pending")
        policy._home_digger_withdraw_pending = True
        return policy

    def test_latch_for_a_deferred_digger_is_released(self):
        policy = self.deferred_shovel_policy()
        self.assertNotIn(STORE_HOME, policy._town_store_attempted)
        key = policy.choose_key(board(turn=101, at=BESIDE))
        self.assertFalse(policy._home_digger_withdraw_pending)
        self.assertNotEqual(policy._shopping_approach_store_type, STORE_HOME)
        self.assertNotIn(policy.last_reason, {"shop:approach", "shop:travel"})
        self.assertIsNotNone(key)

    def test_digger_latch_after_a_closed_home_pass_does_not_route_home(self):
        shelf = wares()
        policy = policy_for(shelf)
        # A stored, servable shovel; the Home pass closed after the queue
        # (home:route-claim-unfulfilled sets the stay's Home attempt).
        policy._home_digger_withdraw_pending = True
        policy._set_town_store_attempted(STORE_HOME, 99, "home-capture-complete")
        policy.choose_key(board(turn=101, at=BESIDE))
        self.assertNotEqual(policy._shopping_approach_store_type, STORE_HOME)

    def test_queued_take_past_the_home_visit_bound_does_not_route_home(self):
        shelf = wares()
        policy = policy_for(shelf)
        policy._home_pending_item = policy._item_signature(shelf[LATER])
        policy._home_withdrawal_queued = True
        ledger = policy._town_visit_ledger
        ledger.approach_fails[STORE_HOME] = policy._town_store_visit_limit(STORE_HOME)
        self.assertNotEqual(policy._next_required_store_type(
            board(turn=101, at=BESIDE)), STORE_HOME)


class ErrandTakeRefusedByPackBudgetTest(unittest.TestCase):
    """life-153: a filed errand take the pack budget refuses gives way."""

    def setUp(self):
        self.sword = store_item("w", 23, 8, name="small sword (1d6) (+0,+0) {Q34}",
                                is_equipment=True)
        self.shelf = shelf_with(SWORD, self.sword, bolts=30)
        policy = policy_for(self.shelf, nineteen_item_pack())
        # Filed while the pack had room (the filing applies the same budget).
        self.assertTrue(policy._file_home_errand(
            board(nineteen_item_pack(17), turn=101), HomeErrandRequest(
                policy._item_signature(self.sword), 1, "home-catalog",
                "identification-catalog"),
            knowledge_current=True))
        policy._shopping_approach_store_type = STORE_HOME
        self.policy = policy

    def test_outside_composer_takes_the_queued_bolts(self):
        policy = self.policy
        bolts = policy._item_signature(self.shelf[BOLTS])
        policy._home_pending_item = bolts
        policy._home_pending_quantity = 11
        policy._home_pending_quantities[bolts] = 11
        policy._home_withdrawal_queued = True
        key = policy.choose_key(board(nineteen_item_pack(), turn=102))
        # Recorded: nothing composed outside, Home re-entered for a deposit.
        self.assertEqual((key, policy.last_reason), ("5 pg11\r\x1b", "home:atomic-withdraw"))
        self.assertFalse(policy._home_errand.active)

    def test_open_home_page_does_not_hand_off_the_refused_take(self):
        policy = self.policy
        page = replace(board(nineteen_item_pack(), turn=102), store=StoreState(
            STORE_HOME, list(self.shelf[:PAGE_SIZE]), stock_num=len(self.shelf),
            page_size=PAGE_SIZE, page_top=0))
        policy.choose_key(page)
        self.assertNotEqual(policy.last_reason, "home:leave-for-pending-withdraw")
        self.assertFalse(policy._home_errand.active)


if __name__ == "__main__":
    unittest.main()
