"""Recorded Q34 pickup/torch loop, 2026-09-28.

Fixture rows are exact state boards at turns 75445, 75453, 75496 and 75507
plus decision identities 50, 51, 55 and 56 from the stopped incident capture.
The post-pickup policy checkpoint is restored before asking the quest executor
for its next action; no live game or bot process is used.
"""

from __future__ import annotations

import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
import test_policy_quest as quest_tests


FIXTURE = Path(__file__).parent / "fixtures" / "newchar-quest34-light-loop-20260928.json.gz"


class NewCharacterLightLoopRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        quest_tests.ApprovedQuestStrategyExecutionTest.setUpClass()
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.rows = json.load(stream)

    def policy(self):
        return quest_tests.ApprovedQuestStrategyExecutionTest()._policy(q34_opening_light=True)

    def board(self, turn):
        return parse_snapshot(self.rows["states"][str(turn)])

    def test_recorded_chain_and_fuel_ping_pong_are_pinned(self):
        decisions = self.rows["decisions"]
        self.assertEqual(
            [(decisions[str(n)]["reason"], decisions[str(n)]["key"])
             for n in (50, 51, 55, 56)],
            [("quest-strategy:pickup-opening-lantern", "g"),
             ("quest:blocked:execute", "5"),
             ("wield-light", "wb"), ("wield-light", "wb")],
        )
        before = self.board(75496)
        after = self.board(75507)
        worn = next(item for item in before.equipment if item.is_torch)
        packed = next(item for item in before.inventory if item.slot == "b")
        self.assertEqual((worn.fuel, packed.fuel), (2493, 2500))
        self.assertEqual(
            next(item for item in after.equipment if item.is_torch).fuel, 2499
        )
        self.assertTrue(any(item.is_lantern and not item.known for item in before.inventory))

    def test_visible_own_square_prevents_repeated_torch_swap(self):
        policy = self.policy()
        for turn in (75496, 75507):
            with self.subTest(turn=turn):
                board = self.board(turn)
                self.assertTrue(board.can_see_own_grid)
                self.assertFalse(board.grid_at(board.player.position).lit)
                self.assertFalse(policy._is_dark(board))
                self.assertIsNone(policy._darkness_recovery_key(board))
                self.assertIsNone(policy._light_to_wield(board))

    def test_worn_torch_fuel_rule_cannot_flip_on_next_turn(self):
        policy = self.policy()
        board = self.board(75496)
        self.assertIsNone(policy._darkness_torch(board))
        # Even a contradictory darkness observation cannot make 2500 turns
        # strictly better than this healthy 2493-turn worn torch.
        dark = replace(board, can_see_own_grid=False)
        self.assertIsNone(policy._darkness_recovery_key(dark))
        worn = next(item for item in board.equipment if item.is_torch)
        depleted = replace(board, equipment=[
            replace(item, fuel=0) if item is worn else item
            for item in board.equipment
        ])
        self.assertEqual(policy._darkness_torch(depleted).slot, "b")

    def test_post_pickup_restored_checkpoint_equips_unknown_lantern(self):
        policy = self.policy()
        pickup = self.board(75445)
        policy._build_grid_index(pickup)
        self.assertEqual(policy._quest_execute_key(pickup, [], []), "g")
        self.assertEqual(policy.last_reason, "quest-strategy:pickup-opening-lantern")
        restored = restore_checkpoint(HengbotPolicy, checkpoint(policy))
        carried = self.board(75453)
        restored._build_grid_index(carried)
        self.assertIsNone(restored._darkness_recovery_key(carried))
        self.assertEqual(restored._quest_execute_key(carried, [], []), "we")
        self.assertEqual(restored.last_reason, "quest-strategy:equip-opening-lantern")
        self.assertFalse(restored._equip_blocked_by_identification(
            next(item for item in carried.equipment if item.is_torch)
        ))
        self.assertTrue(restored._equip_blocked_by_identification(
            next(item for item in carried.inventory if item.is_lantern)
        ))


if __name__ == "__main__":
    unittest.main()
