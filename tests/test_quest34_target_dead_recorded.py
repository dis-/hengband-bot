"""Recorded Q34 cloaker kill must advance the approved ordered strategy."""

from __future__ import annotations

import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path

import tests  # noqa: F401 -- bare module runs must isolate live runtime files
import test_policy_quest as quest_tests
from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
from hengbot.model import Position, parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import POLICY_FINAL_STOP_REASONS, WAIT_KEY


FIXTURE = Path(__file__).parent / "fixtures" / "quest34-target-dead-20260928.json.gz"


class Quest34TargetDeadRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        quest_tests.ApprovedQuestStrategyExecutionTest.setUpClass()
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.rows = json.load(stream)

    def policy(self):
        return quest_tests.ApprovedQuestStrategyExecutionTest()._q34_source_policy()

    def board(self, name, policy):
        return parse_snapshot(self.rows["states"][name], policy._monrace_knowledge)

    def test_capture_pins_the_kill_and_empty_lit_cell(self):
        throw = self.rows["decisions"]["throw"]
        wait = self.rows["decisions"]["wait"]
        self.assertEqual(
            (throw["turn"], throw["position"], throw["reason"], throw["key"]),
            (76590, {"y": 7, "x": 13}, "quest-strategy:throw-torch", "vc6"),
        )
        self.assertEqual(
            (wait["turn"], wait["reason"], wait["key"]),
            (76603, "quest:blocked:fixed-target-not-visible", "5"),
        )
        policy = self.policy()
        before = self.board("throw", policy)
        killed = self.board("kill", policy)
        later = self.board("wait", policy)
        target = Position(7, 15)
        self.assertEqual((before.player.position, killed.player.position),
                         (Position(7, 13), Position(7, 13)))
        self.assertEqual(killed.light_radius, 2)
        self.assertTrue(any(m.race_id == 243 for m in before.visible_monsters))
        self.assertFalse(any(m.race_id == 243 for m in killed.visible_monsters))
        self.assertTrue(any("クローカーを倒した" in msg for msg in killed.messages))
        self.assertTrue(killed.grid_at(target).known)
        self.assertEqual(killed.grid_at(target).map_lighting, 1)
        self.assertTrue(killed.grid_at(target).currently_observed)
        self.assertFalse(killed.grid_at(target).has_monster)
        self.assertEqual(killed.quests[34].status, 1)
        self.assertEqual(later.grid_at(target).map_lighting, 1)
        self.assertFalse(later.grid_at(target).has_monster)

    def test_kill_advances_to_recovery_and_survives_checkpoint(self):
        policy = self.policy()
        before = self.board("throw", policy)
        policy._build_grid_index(before)
        self.assertEqual(
            policy._approved_quest_strategy_key(before, before.visible_monsters, []),
            "vc6",
        )
        killed = self.board("kill", policy)
        restored = restore_checkpoint(HengbotPolicy, checkpoint(policy))
        for label, runner, expected_first in (
            ("live", policy, "quest-strategy:recovery-complete"),
            ("restored", restored, "quest-strategy:recovery-complete"),
            ("cold", self.policy(), "quest-strategy:survey-target-cleared"),
        ):
            with self.subTest(label=label):
                runner._build_grid_index(killed)
                key = runner._approved_quest_strategy_key(
                    killed, killed.visible_monsters, []
                )
                self.assertEqual(key, WAIT_KEY)
                self.assertEqual(runner.last_reason, expected_first)
                self.assertIn((243, 7, 15),
                              runner._quest_strategy_cleared_targets[34])
                if label == "cold":
                    self.assertEqual(
                        runner._quest_strategy_pending_recovery[34]["target"], [7, 15]
                    )
                else:
                    self.assertNotIn(34, runner._quest_strategy_pending_recovery)
                runner._build_grid_index(killed)
                next_key = runner._approved_quest_strategy_key(
                    killed, killed.visible_monsters, []
                )
                if label == "cold":
                    self.assertEqual(runner.last_reason,
                                     "quest-strategy:recovery-complete")
                    self.assertEqual(next_key, WAIT_KEY)
                    runner._build_grid_index(killed)
                    next_key = runner._approved_quest_strategy_key(
                        killed, killed.visible_monsters, []
                    )
                self.assertEqual(runner.last_reason,
                                 "quest-strategy:survey-throw-point")
                self.assertNotEqual(next_key, WAIT_KEY)

    def test_unobservable_target_stays_uncleared_and_stops(self):
        policy = self.policy()
        killed = self.board("kill", policy)
        target = Position(7, 15)
        dark = replace(killed, grids={
            **killed.grids,
            target: replace(killed.grid_at(target), in_view=False, map_lighting=2),
        })
        policy._build_grid_index(dark)
        self.assertEqual(
            policy._approved_quest_strategy_key(dark, [], []), WAIT_KEY
        )
        self.assertEqual(policy.last_reason,
                         "quest:blocked:fixed-target-not-visible")
        self.assertIn(policy.last_reason, POLICY_FINAL_STOP_REASONS)
        self.assertNotIn((243, 7, 15),
                         policy._quest_strategy_cleared_targets[34])
        self.assertNotIn(34, policy._quest_strategy_pending_recovery)


if __name__ == "__main__":
    unittest.main()
