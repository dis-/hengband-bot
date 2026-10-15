from __future__ import annotations

import gzip
import json
import unittest
import tests  # noqa: F401
from dataclasses import replace
from pathlib import Path

from hengbot.model import parse_snapshot, Position, Snapshot
from hengbot.policy import HengbotPolicy
import test_policy_quest as quest_tests
from policy_fixtures import grid, item, player


FIXTURE = Path(__file__).parent / "fixtures" / "q34-opening-oil-20261016.jsonl.gz"


class Q34OpeningOilRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        quest_tests.ApprovedQuestStrategyExecutionTest.setUpClass()
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.rows = {row["turn"]: row for row in map(json.loads, stream)}

    def policy(self):
        return quest_tests.ApprovedQuestStrategyExecutionTest()._policy(
            q34_opening_light=True
        )

    def board(self, turn):
        return parse_snapshot(
            self.rows[turn],
            {
                107: quest_tests.MonraceKnowledge(10, 110, False, False),
                174: quest_tests.MonraceKnowledge(10, 110, False, False),
                243: quest_tests.MonraceKnowledge(10, 110, False, False),
            },
        )

    def test_opening_recovers_oil_at_9_20_before_the_lantern(self):
        policy = self.policy()
        board = self.board(75392)
        policy._build_grid_index(board)
        self.assertEqual(board.player.position, Position(9, 20))
        self.assertEqual(board.grid_at(Position(9, 20)).object_tvals,
                         (quest_tests.TVAL_FLASK,))
        self.assertFalse(any(it.is_oil for it in board.inventory))

        self.assertEqual(policy._approved_quest_strategy_key(board, [], []), "g")
        self.assertEqual(policy.last_reason, "quest-strategy:pickup-opening-oil")

        # DECLARED CONSTRUCTED: remove the floor flask and verify the opening
        # continues to the lantern rather than blocking on optional fuel.
        absent = replace(
            board,
            grids={
                **board.grids,
                Position(9, 20): replace(
                    board.grid_at(Position(9, 20)),
                    object_count=0,
                    object_tvals=(),
                ),
            },
        )
        absent_policy = self.policy()
        absent_policy._build_grid_index(absent)
        self.assertEqual(
            absent_policy._approved_quest_strategy_key(absent, [], []), "2"
        )
        self.assertEqual(absent_policy.last_reason,
                         "quest-strategy:approach-opening-lantern")

        # DECLARED CONSTRUCTED: the real captured after-pickup board is absent;
        # model one pickup result and prove the unchanged lantern step follows.
        oil = item("o", quest_tests.TVAL_FLASK, quest_tests.SV_FLASK_OIL,
                   fuel=7500)
        carried = replace(
            board,
            grids={**board.grids,
                   Position(9, 20): grid(9, 20, in_view=True)},
            inventory=[*board.inventory, oil],
        )
        policy._build_grid_index(carried)
        key = policy._approved_quest_strategy_key(carried, [], [])
        self.assertEqual((key, policy.last_reason),
                         ("2", "quest-strategy:approach-opening-lantern"))

    def test_lantern_pickup_and_equip_controls_remain(self):
        policy = self.policy()
        floor_lantern = self.board(75402)
        policy._build_grid_index(floor_lantern)
        self.assertEqual(
            policy._approved_quest_strategy_key(floor_lantern, [], []), "g"
        )
        self.assertEqual(policy.last_reason,
                         "quest-strategy:pickup-opening-lantern")

        carried_lantern = self.board(75413)
        policy._build_grid_index(carried_lantern)
        self.assertEqual(
            policy._approved_quest_strategy_key(carried_lantern, [], []), "wd"
        )
        self.assertEqual(policy.last_reason,
                         "quest-strategy:equip-opening-lantern")

    def test_dry_lantern_refills_before_darkness_recovery(self):
        board = self.board(76552)
        policy = self.policy()
        board = replace(
            board,
            player=replace(board.player, two_weapon_skill=0, shield_skill=0),
        )
        oil = item("o", quest_tests.TVAL_FLASK, quest_tests.SV_FLASK_OIL,
                   fuel=7500)
        # DECLARED CONSTRUCTED: add the flask to this captured dry-lantern board.
        refuelled = replace(board, inventory=[*board.inventory, oil])

        self.assertEqual(policy.choose_key(refuelled), r"\Fo")
        self.assertEqual(policy.last_reason, "refill-light")
        self.assertEqual(policy._light_refill_item(refuelled), oil)

    def test_dry_lantern_without_oil_does_not_ping_pong(self):
        policy = self.policy()
        dry = self.board(76552)
        # DECLARED CONSTRUCTED: the dry lamp's dark own-square observation is
        # needed to replay the darkness-recovery owner on this captured row.
        dry = replace(
            dry,
            can_see_own_grid=False,
            player=replace(dry.player, two_weapon_skill=0, shield_skill=0),
        )
        first_key = policy.choose_key(dry)
        self.assertEqual((first_key, policy.last_reason),
                         ("wc", "wield-light"))

        # DECLARED CONSTRUCTED: apply the first decision's torch-for-lantern
        # equipment change to represent the next real policy observation.
        lantern = next(it for it in dry.equipment if it.is_lantern)
        torch = next(it for it in dry.inventory if it.is_torch and it.fuel > 0)
        next_board = replace(
            dry,
            player=replace(dry.player),
            can_see_own_grid=True,
            light_radius=1,
            grids={
                **dry.grids,
                dry.player.position: replace(
                    dry.grid_at(dry.player.position), lit=True
                ),
            },
            inventory=[
                *(it for it in dry.inventory if it is not torch),
                replace(lantern, slot="f", is_equipment=False),
            ],
            equipment=[
                *(it for it in dry.equipment if it is not lantern),
                replace(torch, slot="light", is_equipment=True),
            ],
        )
        policy._build_grid_index(next_board)
        key = policy.choose_key(next_board)
        self.assertNotEqual(key, "wd")
        self.assertEqual(key, "5")
        self.assertEqual(policy.last_reason,
                         "quest:blocked:opening-lantern-unfuelled")

    def test_fueled_lantern_is_not_refilled_and_town_keeps_working_light(self):
        policy = self.policy()
        board = self.board(76552)
        worn = next(it for it in board.equipment if it.is_lantern)
        oil = item("o", quest_tests.TVAL_FLASK, quest_tests.SV_FLASK_OIL,
                   fuel=7500)
        fueled = replace(
            board,
            equipment=[replace(worn, known=True, fuel=7500)],
            inventory=[*board.inventory, oil],
        )
        self.assertIsNone(policy._light_refill_item(fueled))
        fueled_policy = self.policy()
        fueled = replace(
            fueled,
            player=replace(
                fueled.player, two_weapon_skill=0, shield_skill=0
            ),
        )
        self.assertNotEqual(fueled_policy.choose_key(fueled), r"\Fo")
        self.assertNotEqual(fueled_policy.last_reason, "refill-light")

        town_policy = HengbotPolicy()
        working_torch = item(
            "light", quest_tests.TVAL_LITE, quest_tests.SV_LITE_TORCH,
            fuel=2000, is_equipment=True,
        )
        empty_lantern = item(
            "l", quest_tests.TVAL_LITE, quest_tests.SV_LITE_LANTERN,
            fuel=0,
        )
        town = Snapshot(
            player(10, 10), {Position(10, 10): grid(10, 10)}, [],
            inventory=[empty_lantern, oil], equipment=[working_torch],
            town_flag=True,
        )
        self.assertIsNone(town_policy._empty_lantern_to_restore(town))
        self.assertIsNone(town_policy._light_to_wield(town))


if __name__ == "__main__":
    unittest.main()
