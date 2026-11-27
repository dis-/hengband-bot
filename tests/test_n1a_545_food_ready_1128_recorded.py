"""Food one trip's worth departs; a carried food stack takes the store's like ware (n1-a life-545,
MAINTAINABILITY.md 2-4).

Recorded (tests/extract_n1a_545_food_ready_1128_fixture.py, ``n1a-545-food-ready-1128``): the
town-arrival checkpoint of 2026-11-28 04:00:06 (Amberite Rogue CL39, Sorcery, speed +7, worn
regeneration, arrival turn 6836403) after a 45F dive.  The Black Market tour went to the second town
(row 65) and spent about 64000 gold there; row 203 saw that town's General Store with 99 Rations
at 3 gold and four Elvish Waybread at 37, left without buying, and row 275 stopped as
town:blocked:survival:food_ready with 7278 gold and 19 of the 23 pack slots used (4 free, the
reserve MIN_TERMINAL_FREE_PACK_SLOTS).

Food is counted by nutrition (food_supply): 2 Hard Biscuits (500), 3 Slime Molds (3000) and 4
Elvish Waybread (7500) are 40000, 8 Rations' worth.  The character digests 17 (speed +7,
speed-table.cpp) + 20 (regeneration) every 50 game turns (digestion-processor.cpp:38-58), so one
planned trip (50000 game turns) eats 37000, 8 Rations; the departure target is 8 + 1 margin = 9.

Why nothing was bought: a Ration stack needs a new pack slot, which the reserve refuses; the
Waybread would have joined the carried stack (food stacks whatever its identification,
item-entity.cpp:1042-1045), but the store's ware is *identified* (fully_known) and the carried one
is not, so the one-slot estimate (town_pack_budget.incoming_slots) counted a new slot as well.

Every row before row 203 is replayed through the public ``choose_key`` and compared with the record
(the town-arrival checkpoint, its journal and sidecars).  Rows 71-179 (the equipment transaction at
the second town's Home) do not reproduce on the current build with or without this fix (the
recorded keys are posted, the replay re-converges at row 180); they are listed, not asserted.

DECLARED CONSTRUCTED: to follow the recorded visit to its stop, the replay holds the stacking fix off
(the consumable similarity fields set back to the full tuple) -- with it the fixed policy buys the
Waybread at row 203 and the visit never reaches the stop.  The give-way is then read on the
recorded stop board with only the stacking fix held off.  The below-trip test removes three of the
four carried Waybread from the row-203 board.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import dataclasses
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import food_supply, town_pack_budget
from hengbot.latch_onset_capture import checkpoint_bytes, restore_checkpoint_bytes
from hengbot.model import TVAL_FOOD
from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from hengbot.policy_constants import MIN_TERMINAL_FREE_PACK_SLOTS, PACK_CAPACITY
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-545-food-ready-1128"
GENERAL_ROW = 203
STOP_ROW = 275
UNREPRODUCED = range(71, 180)
GENERAL_RECORDED = ("\x1b", "town-progress-invariant:continue-observed-shop")
STOP = ("5", "town:blocked:survival:food_ready")
SV_RATION, SV_WAYBREAD = 35, 37


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


def stacking_held_off():
    return mock.patch.object(town_pack_budget, "_CONSUMABLE_SIMILARITY_FIELDS",
                             town_pack_budget._SIMILARITY_FIELDS)


class FoodReady545RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, journal, steps = load(FIXTURE, Path(cls.scratch.name))
        cls.recorded = {row: (journal[row]["key"], journal[row]["reason"])
                        for row in (GENERAL_ROW, STOP_ROW)}
        cls.replayed = []
        with stacking_held_off():
            for row, (recorded, supply) in enumerate(steps[:STOP_ROW + 1]):
                board = supply()
                if row == GENERAL_ROW:
                    cls.general_board, cls.general_checkpoint = board, checkpoint_bytes(policy)
                if row == STOP_ROW:
                    cls.stop_board, cls.stop_checkpoint = board, checkpoint_bytes(policy)
                    break
                key, reason, _ = decide(policy, board)
                cls.replayed.append(((key, reason), (recorded["key"], recorded["reason"])))
                post(policy, recorded["key"])

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def setUp(self):
        self.assertEqual(self.recorded[GENERAL_ROW], GENERAL_RECORDED)
        self.assertEqual(self.recorded[STOP_ROW], STOP)

    def test_the_replay_follows_the_record_to_the_stop(self):
        unmatched = [row for row, (decided, recorded) in enumerate(self.replayed)
                     if decided != recorded]
        self.assertTrue(set(unmatched) <= set(UNREPRODUCED), unmatched)
        self.assertEqual(self.replayed[GENERAL_ROW][0], GENERAL_RECORDED)

    def test_food_is_eight_rations_worth_and_one_trip_eats_eight(self):
        policy = restore_checkpoint_bytes(HengbotPolicy, self.stop_checkpoint)
        board = self.stop_board
        player = board.player
        self.assertEqual((player.food_state, player.gold, player.speed), ("normal", 7278, 117))
        self.assertEqual(PACK_CAPACITY - len(board.inventory), MIN_TERMINAL_FREE_PACK_SLOTS)
        self.assertEqual(food_supply.carried_food_value(board.inventory), 40000)
        self.assertEqual(food_supply.digestion_per_interval(player), 37)
        self.assertEqual(food_supply.trip_rations(player), 8)
        status = policy._supply_ledger(board, policy._planned_depth())["food"]
        self.assertEqual((status.count, status.required_departure), (8, 9))
        self.assertFalse(policy._food_ready(board))
        self.assertTrue(policy._food_adequate(board))
        self.assertFalse(food_supply.below_trip(player, board.inventory))

    def test_the_stores_waybread_joins_the_carried_stack(self):
        board = self.general_board
        carried = next(item for item in board.inventory
                       if (item.tval, item.sval) == (TVAL_FOOD, SV_WAYBREAD))
        ware = next(item for item in board.store.items
                    if (item.tval, item.sval) == (TVAL_FOOD, SV_WAYBREAD))
        ration = next(item for item in board.store.items
                      if (item.tval, item.sval) == (TVAL_FOOD, SV_RATION))
        self.assertEqual((carried.fully_known, ware.fully_known), (False, True))
        self.assertEqual(town_pack_budget.incoming_slots(board, ware, 1), 0)
        self.assertEqual(town_pack_budget.incoming_slots(board, ration, 1), 1)
        with stacking_held_off():
            self.assertEqual(town_pack_budget.incoming_slots(board, ware, 1), 1)

    def test_the_general_store_sells_the_waybread(self):
        policy = restore_checkpoint_bytes(HengbotPolicy, self.general_checkpoint)
        key, reason, _ = decide(policy, self.general_board)
        self.assertEqual(reason, "shop:in-store-buy")
        letter = next(item.letter for item in self.general_board.store.items
                      if (item.tval, item.sval) == (TVAL_FOOD, SV_WAYBREAD))
        self.assertEqual(key, f"p{letter}1\r\r")

    def test_the_stop_board_departs_with_one_trips_food(self):
        policy = restore_checkpoint_bytes(HengbotPolicy, self.stop_checkpoint)
        with stacking_held_off():
            minimum = policy._departure_minimum(self.stop_board, policy._planned_depth())
            self.assertTrue(minimum["values"]["food_ready"])
            key, reason, out = decide(policy, self.stop_board)
        self.assertNotEqual((key, reason), STOP)
        self.assertNotIn("blocked", reason)
        self.assertEqual(reason, "town:repetition-depart:recall")
        self.assertTrue(key.startswith("r"), key)
        self.assertIn("<town-end-waived> food_ready", out)
        self.assertEqual(policy._departure_block["town_end_waived"], ["food_ready"])

    def test_food_below_one_trip_may_use_the_reserve(self):
        # DECLARED CONSTRUCTED: one Waybread of the four carried (17500 food, 3 Rations' worth).
        board = self.general_board
        short = dataclasses.replace(board, inventory=tuple(
            dataclasses.replace(item, count=1)
            if (item.tval, item.sval) == (TVAL_FOOD, SV_WAYBREAD) else item
            for item in board.inventory))
        ration = next(item for item in board.store.items
                      if (item.tval, item.sval) == (TVAL_FOOD, SV_RATION))
        self.assertEqual(food_supply.carried_rations(short.inventory), 3)
        self.assertTrue(food_supply.below_trip(short.player, short.inventory))
        self.assertEqual(town_pack_budget.purchase_reserve_use(short, ration),
                         MIN_TERMINAL_FREE_PACK_SLOTS - 1)
        self.assertTrue(town_pack_budget.purchase_fits(short, ration, 5))
        # One trip's food carried: the Ration stack waits on the reserve as before.
        self.assertEqual(town_pack_budget.purchase_reserve_use(board, ration), 0)
        self.assertFalse(town_pack_budget.purchase_fits(board, ration, 1))
        policy = restore_checkpoint_bytes(HengbotPolicy, self.general_checkpoint)
        self.assertFalse(policy._food_adequate(short))
        key, reason, _ = decide(policy, short)
        self.assertEqual(reason, "shop:in-store-buy")
        self.assertTrue(key.startswith("p"), key)


if __name__ == "__main__":
    unittest.main()
