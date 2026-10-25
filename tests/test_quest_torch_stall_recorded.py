"""Q1 carry procurement after Q34: decision-row projections and constructed boards."""
from __future__ import annotations

import tests  # noqa: F401
import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.model import (
    Snapshot, Position, QuestState, StoreState, StoreItem,
    STORE_GENERAL,
    TVAL_SWORD, TVAL_BOW, TVAL_ARROW, TVAL_LITE, SV_LITE_LANTERN,
    SV_LITE_TORCH, TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, SV_SCROLL_TELEPORT,
    TVAL_POTION, SV_POTION_CURE_CRITICAL, SV_POTION_SPEED, SV_POTION_HEALING,
    TVAL_FOOD, TVAL_FLASK, SV_FLASK_OIL, PLAYER_CLASS_WARRIOR,
)
from hengbot.policy_constants import (
    QUEST_STATUS_UNTAKEN, QUEST_STATUS_FINISHED, QUEST_STATUS_TAKEN,
)
from hengbot.policy import HengbotPolicy
from hengbot.quest_knowledge import load_quest_knowledge
from hengbot.quest_strategies import load_quest_strategies
from hengbot.monrace_knowledge import load_monrace_knowledge
from policy_fixtures import grid, item, player

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/quest-torch-stall-20261026.json"
EDIT = Path("C:/hengband/lib/edit")


class QuestTorchStallRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.quests = load_quest_knowledge(EDIT / "quests")
        cls.strategies = load_quest_strategies(ROOT / "strategy/quests")

    def policy(self):
        policy = HengbotPolicy(
            quest_strategies=self.strategies,
            quest_knowledge=self.quests,
            monrace_knowledge=self.monrace,
        )
        # DECLARED CONSTRUCTED: the projected board has an observed empty Home.
        policy.consume_home_knowledge(())
        return policy

    def board(self, case):
        # DECLARED CONSTRUCTED: decision rows omit inventory details, equipment,
        # terrain and shelves. Project measured level/HP/gold/no-torches onto a
        # supplied warrior board. This is not a byte-faithful state replay.
        row = case["decision"]
        actor = row["player"]
        pos = Position(10, 9)
        return Snapshot(
            player(10, 9, level=actor["level"], hp=actor["hp"],
                   max_hp=actor["max_hp"], gold=actor["gold"],
                   class_id=PLAYER_CLASS_WARRIOR, main_hand_blows=2,
                   main_hand_to_h=50, main_hand_to_d=40),
            {pos: grid(10, 9),
             Position(10, 10): replace(grid(10, 10), store_number=STORE_GENERAL),
             Position(11, 9): grid(11, 9, building_special=1)},
            [], town_flag=True, town_id=0, floor_key=(0, 0, 0),
            turn=row["turn"],
            quests={1: QuestState(1, status=QUEST_STATUS_UNTAKEN, fixed=True, level=5),
                    34: QuestState(34, status=QUEST_STATUS_FINISHED, fixed=True, level=5)},
            inventory=[
                item("a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=10),
                item("b", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=15),
                item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=10),
                item("d", TVAL_POTION, SV_POTION_SPEED, count=10),
                item("e", TVAL_POTION, SV_POTION_HEALING, count=3),
                item("f", TVAL_FOOD, 35, count=10),
                item("g", TVAL_FLASK, SV_FLASK_OIL, count=5, fuel=7500),
                item("h", TVAL_ARROW, 1, count=99),
            ],
            equipment=[
                item("main_hand", TVAL_SWORD, 1, is_equipment=True,
                     damage_dice_num=2, damage_dice_sides=6, to_h=10, to_d=10),
                item("bow", TVAL_BOW, 12, is_equipment=True),
                item("light", TVAL_LITE, SV_LITE_LANTERN, fuel=7500,
                     is_equipment=True),
            ],
        )

    def test_saved_decisions_show_the_same_missing_carry_and_no_procurement(self):
        self.assertEqual([c["decision"]["decision_sequence"] for c in self.cases],
                         [18866, 32744])
        for case in self.cases:
            row = case["decision"]
            self.assertEqual(row["procurement_requirements"], [])
            self.assertEqual(row["abandoned_quest_carry_requirements"], {})
            readiness = row["fixedquest_readiness"]
            self.assertEqual((readiness["quest_id"], readiness["verdict"],
                              readiness["reason"]), (1, False, "strategy-force"))
            self.assertEqual(readiness["strategy_force"]["failed"],
                             ["throwing_items.lit_torch"])
            self.assertEqual(readiness["strategy_force"]["carries"], {
                "throwing_items.lit_torch": {
                    "measured": 0, "required": 5, "ready": False,
                },
            })

    def test_public_route_buys_torches_through_executor_then_requests_quest(self):
        from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
        from tests.test_input_executor import (
            FaithfulHookGame, ProductionHarness, command_screen, prompt_screen,
            store_screen,
        )

        for case in self.cases:
            with self.subTest(source=case["source"]):
                policy = self.policy()
                board = self.board(case)
                self.assertFalse(policy._fixed_quest_ready(board, 1))
                self.assertEqual(policy.fixed_quest_readiness_state()[
                    "strategy_force"]["failed"], ["throwing_items.lit_torch"])
                self.assertEqual(policy.choose_key(board), "6")
                self.assertEqual(policy.last_reason, "shop:approach")
                policy.confirm_key_posted("6")

                # DECLARED CONSTRUCTED: stocked shelf and source-derived fuel.
                ware = StoreItem("a", "Torch", 99, TVAL_LITE, SV_LITE_TORCH,
                                 price=1, fuel=2500, aware=True, known=True)
                door = replace(board, player=replace(
                    board.player, position=Position(10, 10)), turn=board.turn + 1)
                inside = replace(door, store=StoreState(STORE_GENERAL, [ware]))
                self.assertEqual(policy.choose_key(inside), "\x1b")
                policy.confirm_key_posted("\x1b")
                outside = replace(door, turn=door.turn + 1)
                entry = policy.choose_key(outside)
                self.assertEqual((entry, policy.last_reason), ("5", "shop:one-shot-buy"))

                # DECLARED CONSTRUCTED: the hook harness renders quantity and
                # price prompts, then the actual purchase effect and escape.
                initial = {"turn": outside.turn, "grid_map": {"runs": []},
                           "floor": {"dungeon_id": 0, "level": 0}, "equipment": [],
                           "player": {"gold": board.player.gold}, "inventory": []}
                stock = {"letter": "a", "name": "Torch", "count": 99,
                         "tval": TVAL_LITE, "sval": SV_LITE_TORCH,
                         "fuel": 2500, "price": 1, "aware": True, "known": True}
                shelf = {**initial, "store": {"store_type": STORE_GENERAL, "items": [stock]}}
                final = {**initial, "turn": outside.turn + 2,
                         "player": {"gold": board.player.gold - 10},
                         "inventory": [{"slot": "i", "name": "Torch", "count": 10,
                                        "tval": TVAL_LITE, "sval": SV_LITE_TORCH,
                                        "fuel": 2500, "aware": True, "known": True}]}
                game = FaithfulHookGame()
                game.state = initial
                before_screen = store_screen()
                before_screen["lines"][5] = "a) 99 Torch   1 gold"
                after_screen = store_screen()
                after_screen["lines"][5] = "a) 89 Torch   1 gold"
                game.screens = [before_screen, prompt_screen("Quantity (1-99): 1"),
                                prompt_screen("Buy it? [Y/n]"), after_screen,
                                command_screen(final["turn"])]
                after_shelf = {**final, "store": {
                    "store_type": STORE_GENERAL, "items": [{**stock, "count": 89}]}}
                game.states = [shelf, shelf, shelf, after_shelf, final]
                _game, _client, executor = ProductionHarness.make(self, game)
                self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome,
                                 "ready")
                port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
                posted = set()
                sent, _ = _send_new_decision_key(
                    port, "outside", entry, None, posted, in_store=False,
                    decision={"sequence": 1, "reason": policy.last_reason},
                    snapshot=outside, posting_contract=PostingContract(),
                )
                self.assertTrue(sent)
                policy.confirm_key_posted(entry)
                operation_board = replace(inside, turn=outside.turn + 1)
                operation = policy.choose_key(operation_board)
                self.assertEqual((operation, policy.last_reason),
                                 ("pa10\r\r\x1b", "shop:one-shot-buy"))
                sent, _ = _send_new_decision_key(
                    port, "inside", operation, None, posted, in_store=True,
                    decision={"sequence": 2, "reason": policy.last_reason},
                    snapshot=operation_board, posting_contract=PostingContract(),
                )
                self.assertTrue(sent)
                self.assertEqual(port.last_result.outcome, "completed")
                self.assertEqual(game.accepted, ["5", "pa", "10\r", "\r", "\x1b"])
                policy.reconcile_input_operation(port.last_result.operation.owner,
                                                 port.last_result.operation.business_outcome)
                policy.confirm_key_posted(operation)

                # Project the executor-observed gold and torch stack back onto
                # the same constructed board; no success predicate is patched.
                from hengbot.cli import _parse_items
                observed = executor.ready_board
                bought = replace(door, turn=final["turn"],
                                 player=replace(door.player, gold=observed["player"]["gold"]),
                                 inventory=[*door.inventory, *_parse_items(observed["inventory"])])
                self.assertTrue(policy._fixed_quest_ready(bought, 1))
                readiness = policy.fixed_quest_readiness_state()
                self.assertEqual(readiness["reason"], "ready")
                self.assertEqual(readiness["strategy_force"]["carries"][
                    "throwing_items.lit_torch"],
                    {"measured": 10, "required": 5, "ready": True})
                self.assertEqual(policy.choose_key(bought), "1q\x1b")
                self.assertEqual(policy.last_reason, "fixedquest:request")

    def test_already_carried_torches_still_request_quest_without_purchase(self):
        for case in self.cases:
            policy = self.policy()
            board = self.board(case)
            supplied = replace(board, inventory=[*board.inventory, item(
                "i", TVAL_LITE, SV_LITE_TORCH, count=10, fuel=2500)])
            self.assertEqual(policy.choose_key(supplied), "2q\x1b")
            self.assertEqual(policy.last_reason, "fixedquest:request")

    def test_level_boundary_uses_the_same_existing_procurement_route(self):
        for level in (9, 10, 25):
            with self.subTest(level=level):
                policy = self.policy()
                board = self.board(self.cases[0])
                board = replace(board, player=replace(board.player, level=level))
                self.assertEqual(policy.choose_key(board), "6")
                self.assertEqual(policy.last_reason, "shop:approach")

    def test_non_town_and_taken_heads_do_not_start_carry_procurement(self):
        board = self.board(self.cases[0])
        dungeon = replace(board, town_flag=False, floor_key=(2, 13, 0))
        taken = replace(board, quests={**board.quests, 1: QuestState(
            1, status=QUEST_STATUS_TAKEN, fixed=True, level=5)})
        for observation in (dungeon, taken):
            self.assertIsNone(self.policy()._carry_procurement_strategy(observation))

    def test_lit_count_requires_positive_fuel_in_inventory(self):
        board = self.board(self.cases[0])
        for fuel, expected in ((0, False), (2500, True)):
            policy = self.policy()
            supplied = replace(board, inventory=[*board.inventory, item(
                "i", TVAL_LITE, SV_LITE_TORCH, count=5, fuel=fuel)])
            self.assertEqual(policy._fixed_quest_ready(supplied, 1), expected)
            self.assertEqual(policy.fixed_quest_readiness_state()[
                "strategy_force"]["carries"]["throwing_items.lit_torch"]["measured"],
                5 if expected else 0)


if __name__ == "__main__":
    unittest.main()
