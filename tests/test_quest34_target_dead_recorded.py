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
OPENING_FIXTURE = (
    Path(__file__).parent / "fixtures" / "q34-opening-live-20261011.json.gz"
)


class Quest34TargetDeadRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        quest_tests.ApprovedQuestStrategyExecutionTest.setUpClass()
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.rows = json.load(stream)
        with gzip.open(OPENING_FIXTURE, "rt", encoding="utf-8") as stream:
            cls.opening_rows = json.load(stream)

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

    def test_live_locked_opening_door_is_bounded_and_route_continues(self):
        rows = self.opening_rows
        initial_decision = rows["decisions"]["door_open_attempt"]
        self.assertEqual(
            (initial_decision["turn"], initial_decision["position"],
             initial_decision["reason"], initial_decision["key"]),
            (75789, {"y": 11, "x": 1},
             "quest-strategy:open-opening-door", "o6"),
        )
        failed = self.board_from_opening("door_failed_pick")
        door = failed.grid_at(Position(11, 2))
        self.assertTrue(door.known)
        self.assertTrue(door.is_closed_door)
        self.assertFalse(door.passable)
        self.assertIn("鍵をはずせなかった。", failed.messages)
        self.assertEqual(failed.player.position, Position(11, 1))

        policy = self.policy()
        approach = self.board_from_opening("door_approach", policy=policy)
        results = []
        for _ in range(4):
            policy._build_grid_index(approach)
            results.append((
                policy._approved_quest_strategy_key(
                    approach, approach.visible_monsters, []
                ),
                policy.last_reason,
            ))

        self.assertEqual(results[:3], [
            ("o6", "quest-strategy:open-opening-door"),
            ("o6", "quest-strategy:open-opening-door"),
            ("o6", "quest-strategy:open-opening-door"),
        ])
        self.assertEqual(results[3], ("o6", "quest-strategy:open-opening-door"))
        from hengbot.cli import _cell_loop_guard_applies
        self.assertFalse(_cell_loop_guard_applies(
            approach, "quest-strategy:open-opening-door",
            approach.player.position,
        ))
        opened = self.board_from_opening("door_opened", policy=policy)
        entered = self.board_from_opening("door_entered", policy=policy)
        self.assertIn("鍵をはずした。", opened.messages)
        self.assertEqual(entered.player.position, Position(11, 2))

    def test_opening_door_lock_pick_attempts_end_in_a_visible_stop(self):
        # DECLARED CONSTRUCTED: the attempt counter is set to the bound; the board
        # is the recorded closed-door approach (the cell-loop guard is exempt).
        from hengbot.policy_constants import Q34_OPENING_DOOR_ATTEMPT_LIMIT
        policy = self.policy()
        approach = self.board_from_opening("door_approach", policy=policy)
        policy._build_grid_index(approach)
        policy._q34_opening_door_attempts = Q34_OPENING_DOOR_ATTEMPT_LIMIT
        key = policy._approved_quest_strategy_key(
            approach, approach.visible_monsters, []
        )
        self.assertEqual(
            (key, policy.last_reason),
            (WAIT_KEY, "quest:blocked:q34-opening-door-locked"),
        )
        self.assertIn(policy.last_reason, POLICY_FINAL_STOP_REASONS)

    def test_live_q34_torch_kill_is_confirmed_by_the_defeat_message(self):
        rows = self.opening_rows
        throw1 = rows["decisions"]["torch_throw_1"]
        throw2 = rows["decisions"]["torch_throw_2"]
        blocked = rows["decisions"]["blocked_after_kill"]
        self.assertEqual(
            [(d["turn"], d["position"], d["reason"], d["key"])
             for d in (throw1, throw2)],
            [
                (76727, {"y": 7, "x": 13}, "quest-strategy:throw-torch", "vc6"),
                (76737, {"y": 7, "x": 13}, "quest-strategy:throw-torch", "vc6"),
            ],
        )
        self.assertEqual(
            (blocked["turn"], blocked["reason"], blocked["key"]),
            (76746, "quest:blocked:fixed-target-not-visible", "5"),
        )
        killed = self.board_from_opening("cloaker_killed")
        self.assertTrue(killed.player.melee_displayed_totals)
        self.assertEqual(killed.player.position, Position(7, 13))
        self.assertEqual(killed.light_radius, 2)
        self.assertFalse(any(m.race_id == 243 for m in killed.visible_monsters))
        self.assertIn("松明(1500ターンの寿命) {@v0=g}がクローカーに命中した。",
                      killed.messages)
        self.assertIn("クローカーを倒した。", killed.messages)
        target = killed.grid_at(Position(7, 15))
        between = killed.grid_at(Position(7, 14))
        self.assertTrue(target.known and target.currently_observed)
        self.assertFalse(target.in_view)
        self.assertEqual(target.map_lighting, 1)
        self.assertFalse(target.has_monster)
        self.assertTrue(between.currently_observed)
        self.assertEqual(between.map_lighting, 1)
        self.assertTrue(between.allows_los)

        # The new protocol-3 symbol cannot certify the empty cell
        # (test_protocol3_display_align); the game's defeat message can, once
        # the bot has seen the cloaker by name on the previous board.
        policy = self.policy()
        hit = self.board_from_opening("first_torch_hit", policy=policy)
        self.assertTrue(any(m.race_id == 243 for m in hit.visible_monsters))
        policy._build_grid_index(hit)
        policy._approved_quest_strategy_key(hit, hit.visible_monsters, [])
        policy._build_grid_index(killed)
        policy._approved_quest_strategy_key(killed, [], [])
        self.assertIn((243, 7, 15), policy._quest_strategy_cleared_targets[34])
        self.assertNotEqual(policy.last_reason, "quest:blocked:fixed-target-not-visible")

        # Control: the same boards without the defeat message stay uncleared.
        silent = self.policy()
        hit = self.board_from_opening("first_torch_hit", policy=silent)
        silent._build_grid_index(hit)
        silent._approved_quest_strategy_key(hit, hit.visible_monsters, [])
        quiet = replace(killed, messages=tuple(
            message for message in killed.messages if "を倒した" not in message))
        silent._build_grid_index(quiet)
        silent._approved_quest_strategy_key(quiet, [], [])
        self.assertNotIn((243, 7, 15), silent._quest_strategy_cleared_targets.get(34, set()))

    def board_from_opening(self, name, policy=None):
        policy = policy or self.policy()
        return parse_snapshot(
            self.opening_rows["states"][name], policy._monrace_knowledge
        )


if __name__ == "__main__":
    unittest.main()
