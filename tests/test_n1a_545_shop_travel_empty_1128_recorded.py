"""A shed the store cannot sell leaves the page and departs, never an empty key (n1-a life-545,
MAINTAINABILITY.md 2-3).

Recorded (tests/extract_n1a_545_shop_travel_empty_1128_fixture.py,
``n1a-545-shop-travel-empty-1128``): the town-arrival checkpoint of 2026-11-28 08:42:10 (Amberite
Rogue CL38, build bot-b3b1efe59, arrival turn 7149782), 200 rows.  Row 197 stepped off the
entrance at the town end; the town end's weight rescue (departure_rescues ``overweight-give-way``,
overweight_departure ``relief_spent_key``, 24cfaaf12) found 198.4 lb on a 165.0 lb limit, 0.5 lb
over the 197.9 lb that costs no speed (player-speed.cpp:43-51), every stack retained
(``retained-only``), so it opened the relief and shed 3 of the 8 Hard Biscuits (the cheapest
reserved weight, ``shed_candidates``) to the General Store.  Row 198 travelled there; on row 199,
inside the store, the sale composed nothing -- the reservation refuses a sale of the reserved
food (``store_item_key`` -> None, ``_batch_sale_entry`` None, ``_batch_sell_key`` ``""``) -- and
``_overweight_surplus_sale_key`` returned that ``""``: the driver halted with no-key-exhausted.

The fix: an uncomposable shed sale gives way with ``force`` (what cannot be shed departs, the
2026-11-27 rule) and leaves the page.

Every row is replayed through the public ``choose_key`` posting the recorded key.  Rows from 9 on
do not all reproduce: the equipment search runs under a wall-clock budget
(equipment_optimizer ``timeout_seconds``), so its plan differs between machines and runs; those
rows are listed, not asserted.  Rows 198 and 199 reproduce (the travel and the empty key).

DECLARED CONSTRUCTED: the departure after the page is left is read on the recorded row-198 board
(the outside board the travel left from; the store page has no town map).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import overweight_departure
from hengbot.latch_onset_capture import checkpoint_bytes, restore_checkpoint_bytes
from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from hengbot.policy_constants import LEAVE_STORE_KEY
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-545-shop-travel-empty-1128"
TRAVEL_ROW, STOP_ROW = 198, 199
TRAVEL = ("\x1b`n!.", "shop:travel")
STOP = ("", "shop:travel")
GENERAL_STORE = 0


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


def decide(policy, board):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        key = policy.choose_key(board)
    return key, policy.last_reason, out.getvalue()


class ShopTravelEmpty545RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, journal, steps = load(FIXTURE, Path(cls.scratch.name))
        cls.recorded = {row: (journal[row]["key"], journal[row]["reason"])
                        for row in (TRAVEL_ROW, STOP_ROW)}
        cls.decided = []
        for row, (recorded, supply) in enumerate(steps):
            board = supply()
            if row == TRAVEL_ROW:
                cls.outside_board = board
            if row == STOP_ROW:
                cls.stop_board, cls.stop_checkpoint = board, checkpoint_bytes(policy)
            key, reason, _ = decide(policy, board)
            cls.decided.append((key, reason))
            post(policy, recorded["key"])

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def test_the_recorded_rows(self):
        self.assertEqual(self.recorded[TRAVEL_ROW], TRAVEL)
        self.assertEqual(self.recorded[STOP_ROW], STOP)
        self.assertEqual(self.decided[TRAVEL_ROW], TRAVEL)

    def test_the_whole_visit_decides_no_empty_key(self):
        self.assertEqual(len(self.decided), STOP_ROW + 1)
        self.assertEqual([row for row, (key, _) in enumerate(self.decided) if not key], [])

    def test_the_shed_is_reserved_food_over_the_tolerated_weight(self):
        policy, board = restore_checkpoint_bytes(HengbotPolicy, self.stop_checkpoint), self.stop_board
        self.assertEqual(board.store.store_type, GENERAL_STORE)
        weight, limit = policy._inventory_weight(board), policy._inventory_weight_limit(board)
        self.assertEqual((weight, limit, overweight_departure.tolerated_weight(limit)),
                         (1984, 1650, 1979))
        self.assertEqual(policy._weight_relief_selection(board).route, "retained-only")
        pending = policy._overweight_surplus_disposal["pending"]
        self.assertEqual((pending["count"], pending["mode"], pending["posted"]), (3, "sale", False))
        item = next(item for item in board.inventory
                    if policy._sale_item_identity(item) == pending["identity"])
        self.assertEqual(policy._retention_surplus(board, item), 0)

    def test_the_stop_board_leaves_the_store_and_departs(self):
        policy = restore_checkpoint_bytes(HengbotPolicy, self.stop_checkpoint)
        key, reason, out = decide(policy, self.stop_board)
        self.assertEqual((key, reason), (LEAVE_STORE_KEY, "shop:leave-overweight-surplus"))
        self.assertIn("<overweight-departure-waived> cause=shed-sale-uncomposable weight=1984 "
                      "limit=1650 allowed=1984 forced=True", out)
        self.assertFalse(policy._inventory_overweight(self.stop_board))
        post(policy, key)
        reasons = []
        for _ in range(4):
            key, reason, _ = decide(policy, self.outside_board)
            self.assertTrue(key, reason)
            reasons.append(reason)
            post(policy, key)
            if reason.startswith("town:recall-to"):
                break
        self.assertTrue(reasons[-1].startswith("town:recall-to"), reasons)
        self.assertFalse(any("blocked" in reason for reason in reasons), reasons)

    def test_revert_the_uncomposable_sale_returns_the_empty_key(self):
        policy = restore_checkpoint_bytes(HengbotPolicy, self.stop_checkpoint)
        with mock.patch.object(overweight_departure, "sale_uncomposed", lambda _key: False):
            key, reason, _ = decide(policy, self.stop_board)
        self.assertEqual((key, reason), STOP)

if __name__ == "__main__":
    unittest.main()
