"""A hungry ordinary eater buys food at once and carries a trip's food (n1-a life-544, 2026-11-26).

n1-a life-544, Amberite rogue CL14, the first character the bot played that eats ordinary food
(food_type RATION; regeneration innate and on the worn Trump blade, slow digestion on the blade),
starved to death in the Outpost at 23:45:38 with 7310 gold.

* The last dive (Yeek cave, game day 4 01:16-08:32) left with Jerky, a Ration and a Slime Mold
  (the ring's board 287247: 2 Jerky + 1 Ration + 1 Slime Mold = 11000 food): the ledger counted
  food by item, so five Jerky (7500 food) or five Hard Biscuits (2500) met the departure's
  "5 rations".  At 25 food per 50 game turns (speed 110: 10, regeneration +20, slow digestion -5,
  digestion-processor.cpp:38-58) a Ration lasted 9993 game turns (eaten at 294365, hungry at
  304358); the character recalled hungry with nothing edible (310257).
* In town (fixture n1a-544-starvation-1126, town-arrival rows 0-12) the General Store page
  offered 99 Rations at 4 gold, but the outside composer (item_reservation ``store_item_key``)
  refused the new stack against the 4-slot departure reserve (19 of 23 pack slots used): row 9
  stepped off the entrance (``survival:buy-food`` '1'), row 10 stepped on, row 11 left the shop
  unbought (``town-progress-invariant:continue-observed-shop``), about 150 times until death.

Now the survival purchase of ordinary food may use the reserve (town_pack_budget
``survival_food_fits``), the ledger counts Rations' worth of nutrition and sizes the departure
from the board's own digestion (food_supply).

DECLARED CONSTRUCTED: the departure board of ``test_five_jerky_no_longer_meet_the_departure``
(the arrival board with five Jerky added to the pack).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from hengbot import food_supply
from hengbot.cli import _handle_owner_retirement
from hengbot.magic_eater_devices import staple_food
from hengbot.model import AbilitySources, InventoryItem, TVAL_FOOD, TVAL_WAND, parse_snapshot
from hengbot.policy import staged_prompt_chain_matches
from hengbot.policy_constants import FOOD_TYPE_MANA, FOOD_TYPE_RATION
from hengbot.town_pack_budget import survival_food_fits
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-544-starvation-1126"
LOG_ONLY = SimpleNamespace(owner_retired_log_only=True, decision_log=None)
FIRST_PAGE_ROW = 8
STEP_OFF_ROW = 9
SV_RATION, SV_BISCUIT, SV_JERKY, SV_WAYBREAD = 35, 32, 33, 37
PLAYER_CLASS_MAGIC_EATER = 16


def post(policy, board, key, visit_before):
    key = policy.validate_read_key(board, key)
    key = _handle_owner_retirement(LOG_ONLY, board, key, policy, visit_before)
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})
    return key


def dive_boards() -> dict:
    with gzip.open(FIXTURE / "boards.jsonl.gz", "rt", encoding="utf-8") as stream:
        return {row["turn"]: row for row in map(json.loads, stream)}


def player(speed=110, regenerate=(), slow_digest=(), food_type=FOOD_TYPE_RATION, class_id=3):
    return SimpleNamespace(
        speed=speed, food_type=food_type, class_id=class_id,
        ability_sources=AbilitySources({"regenerate": frozenset(regenerate),
                                        "slow_digest": frozenset(slow_digest)}))


def food(sval, count=1, slot="b"):
    return SimpleNamespace(tval=TVAL_FOOD, sval=sval, count=count, aware=True, slot=slot)


class StarvationLoop544RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Rows 0-8 posted as recorded: the policy on the first outside board after the page."""
        scratch = TemporaryDirectory()
        cls.addClassCleanup(scratch.cleanup)
        policy, recorded, steps = load(FIXTURE, Path(scratch.name))
        cls.mismatches = []
        cls.boards = {}
        for row, supply in steps[:STEP_OFF_ROW + 1]:
            board = supply()
            cls.boards[row["row"]] = board
            if row["row"] == STEP_OFF_ROW:
                cls.before_step_off = copy.deepcopy(policy)
                break
            before = copy.copy(policy._store_visit)
            key = policy.choose_key(board)
            if (key, policy.last_reason) != (row["key"], row["reason"]):
                cls.mismatches.append((row["row"], key, policy.last_reason))
            post(policy, board, row["key"], before)
        cls.recorded = recorded

    def test_the_visit_replays_as_recorded_up_to_the_page(self):
        self.assertEqual(self.mismatches, [])
        page = self.boards[FIRST_PAGE_ROW]
        self.assertEqual(page.store.store_type, 0)
        ration = next(item for item in page.store.items if item.sval == SV_RATION)
        self.assertEqual((ration.count, ration.price, ration.letter), (99, 4, "a"))
        self.assertEqual((page.player.gold, len(page.inventory)), (7310, 19))

    def test_the_observed_rations_are_bought_at_once(self):
        policy = copy.deepcopy(self.before_step_off)
        board = self.boards[STEP_OFF_ROW]
        self.assertEqual(board.player.food_state, "hungry")
        key = policy.choose_key(board)
        # Recorded (revert): '1' survival:buy-food, the step off the entrance.
        self.assertEqual((key, policy.last_reason), ("5", "shop:one-shot-buy"))
        # Six Rations: one trip at 25 food per 50 game turns (25000) and one more.
        self.assertEqual(policy._store_visit.operation_key, "pa6\r\r\x1b")

    def test_the_reserve_still_holds_for_other_wares_and_mana_food(self):
        board = self.boards[STEP_OFF_ROW]
        page = self.boards[FIRST_PAGE_ROW].store
        ration = next(item for item in page.items if item.sval == SV_RATION)
        water = next(item for item in page.items if item.tval == 75 and item.sval == 0)
        self.assertTrue(survival_food_fits(board, ration, 6))
        self.assertFalse(survival_food_fits(board, water, 1))
        wand = replace(water, tval=TVAL_WAND, sval=24, name="wand")
        self.assertFalse(survival_food_fits(board, wand, 1))

    def test_five_jerky_no_longer_meet_the_departure(self):
        policy = copy.deepcopy(self.before_step_off)
        board = self.boards[STEP_OFF_ROW]
        jerky = InventoryItem(slot="t", name="乾し肉", tval=TVAL_FOOD, sval=SV_JERKY,
                              count=5, weight=2, aware=True, known=True)
        stocked = replace(board, inventory=(*board.inventory, jerky))
        ledger = policy._supply_ledger(stocked, policy._planned_depth())["food"]
        self.assertEqual((ledger.count, ledger.required_departure), (1, 6))
        self.assertFalse(policy._food_ready(stocked))
        rations = replace(jerky, sval=SV_RATION, name="食料", count=6, weight=10)
        self.assertTrue(policy._food_ready(replace(board, inventory=(*board.inventory, rations))))


class Dive544RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = TemporaryDirectory()
        cls.addClassCleanup(scratch.cleanup)
        cls.policy, _recorded, _steps = load(FIXTURE, Path(scratch.name))
        cls.raw = dive_boards()

    def decide(self, turn):
        policy = copy.deepcopy(self.policy)
        board = parse_snapshot(copy.deepcopy(self.raw[turn]), policy._monrace_knowledge)
        return policy, board, policy.choose_key(board)

    def test_the_board_digests_25_per_50_game_turns(self):
        policy, board, _key = self.decide(287247)
        self.assertEqual(board.player.ability_sources["regenerate"],
                         frozenset({"equipment", "permanent"}))
        self.assertEqual(board.player.ability_sources["slow_digest"], frozenset({"equipment"}))
        self.assertEqual(food_supply.digestion_per_interval(board.player), 25)
        # Recorded: a Ration (5000) eaten at 294365, hungry again at 304358.
        self.assertAlmostEqual(304358 - 294365, 5000 / 25 * 50, delta=20)
        ledger = policy._supply_ledger(board, policy._planned_depth())["food"]
        # 2 Jerky + 1 Ration + 1 Slime Mold = 11000 food: two Rations' worth, not four.
        self.assertEqual((ledger.count, ledger.required_departure), (2, 6))

    def test_hungry_with_food_eats(self):
        _policy, board, key = self.decide(304358)
        self.assertEqual(board.player.food_state, "hungry")
        self.assertEqual(key, "Eb")

    def test_hungry_without_food_returns(self):
        policy, board, _key = self.decide(310257)
        self.assertEqual(policy._find_edible(board), None)
        self.assertTrue(policy.last_reason.startswith("return:"), policy.last_reason)


class FoodSupplyFormulaTest(unittest.TestCase):
    """food_supply against src/player/digestion-processor.cpp:38-58 and speed-table.cpp."""

    def test_energy_table(self):
        for speed, energy in ((0, 1), (70, 2), (100, 5), (109, 9), (110, 10), (119, 19),
                              (120, 20), (130, 30), (137, 36), (140, 38), (150, 42),
                              (160, 45), (170, 47), (199, 49), (250, 49)):
            self.assertEqual(food_supply.speed_to_energy(speed), energy, speed)

    def test_digestion(self):
        self.assertEqual(food_supply.digestion_per_interval(player()), 10)
        self.assertEqual(food_supply.digestion_per_interval(player(regenerate={"permanent"})), 30)
        self.assertEqual(food_supply.digestion_per_interval(
            player(regenerate={"permanent"}, slow_digest={"equipment"})), 25)
        self.assertEqual(food_supply.digestion_per_interval(player(slow_digest={"equipment"})), 5)
        self.assertEqual(food_supply.digestion_per_interval(player(speed=120)), 20)
        # A slowed (overweight) board sizes the trip at normal speed; a spell's
        # regeneration does not last a trip.
        self.assertEqual(food_supply.digestion_per_interval(player(speed=100)), 10)
        self.assertEqual(food_supply.digestion_per_interval(player(regenerate={"temporary"})), 10)

    def test_departure_rations(self):
        self.assertEqual(food_supply.departure_rations(player()), 5)
        self.assertEqual(food_supply.departure_rations(player(regenerate={"permanent"})), 7)
        self.assertEqual(food_supply.departure_rations(
            player(regenerate={"permanent"}, slow_digest={"equipment"})), 6)
        self.assertEqual(food_supply.departure_rations(
            player(speed=130, regenerate={"equipment"})), 11)
        with self.assertRaises(ValueError):
            food_supply.departure_rations(player(food_type=FOOD_TYPE_MANA))

    def test_nutrition(self):
        self.assertEqual(food_supply.carried_rations([food(SV_BISCUIT, 5)]), 0)
        self.assertEqual(food_supply.carried_rations([food(SV_JERKY, 5)]), 1)
        self.assertEqual(food_supply.carried_rations([food(SV_RATION, 5)]), 5)
        self.assertEqual(food_supply.carried_rations([food(SV_WAYBREAD, 2)]), 3)
        self.assertEqual(food_supply.items_for_rations(food(SV_RATION), 6), 6)
        self.assertEqual(food_supply.items_for_rations(food(SV_WAYBREAD), 6), 4)
        self.assertEqual(food_supply.items_for_rations(food(SV_BISCUIT), 1), 10)

    def test_rations_before_biscuits(self):
        biscuit, ration = food(SV_BISCUIT), food(SV_RATION)
        self.assertFalse(food_supply.procurement_food(biscuit, [biscuit, ration]))
        self.assertTrue(food_supply.procurement_food(ration, [biscuit, ration]))
        self.assertTrue(food_supply.procurement_food(biscuit, [biscuit]))

    def test_an_ordinary_food_magic_eater_has_no_staple(self):
        board = SimpleNamespace(player=player(class_id=PLAYER_CLASS_MAGIC_EATER),
                                inventory=())
        self.assertIsNone(staple_food(board))
        self.assertEqual(food_supply.departure_rations(board.player), 5)


if __name__ == "__main__":
    unittest.main()
