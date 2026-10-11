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


OPENING_FIXTURE = (
    Path(__file__).parent / "fixtures" / "q34-opening-live-20261011.json.gz"
)


class Quest34TargetDeadRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        quest_tests.ApprovedQuestStrategyExecutionTest.setUpClass()
        with gzip.open(OPENING_FIXTURE, "rt", encoding="utf-8") as stream:
            cls.opening_rows = json.load(stream)

    def policy(self):
        return quest_tests.ApprovedQuestStrategyExecutionTest()._q34_source_policy()

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
        restored = restore_checkpoint(HengbotPolicy, checkpoint(policy))
        policy._build_grid_index(killed)
        policy._approved_quest_strategy_key(killed, [], [])
        self.assertIn((243, 7, 15), policy._quest_strategy_cleared_targets[34])
        self.assertNotEqual(policy.last_reason, "quest:blocked:fixed-target-not-visible")
        # A checkpoint taken before the kill keeps the seen name: the restored
        # policy also confirms the kill and walks east to recover the torches.
        restored._build_grid_index(killed)
        self.assertEqual(
            restored._approved_quest_strategy_key(killed, [], []), "6"
        )
        self.assertEqual(
            restored.last_reason, "quest-strategy:recover-defeated-target-torches"
        )
        self.assertIn((243, 7, 15), restored._quest_strategy_cleared_targets[34])
        self.assertEqual(
            restored._quest_strategy_pending_recovery[34]["target"], [7, 15]
        )

        # The defeat message can scroll past (2026-10-12 Linux smoke: only the
        # level-up lines arrived). Experience gained right after the throw at
        # this target, which then vanished, also proves the kill.
        gained = self.policy()
        # DECLARED CONSTRUCTED: the stub monster table lacks the cloaker's
        # MonraceDefinitions id 243 values (level 13, exp 30) the kill-share
        # check needs: kill share at max level 2 is 13 * 30 / 4 = 97.5.
        gained._monrace_knowledge[243] = replace(
            gained._monrace_knowledge[243], level=13, experience=30)
        hit = self.board_from_opening("first_torch_hit", policy=gained)
        gained._build_grid_index(hit)
        self.assertEqual(
            gained.last_reason if gained._approved_quest_strategy_key(
                hit, hit.visible_monsters, []) else None,
            "quest-strategy:throw-torch",
        )
        no_message = replace(killed, messages=tuple(
            message for message in killed.messages if "を倒した" not in message))
        self.assertGreater(no_message.player.exp, hit.player.exp)
        # DECLARED CONSTRUCTED: the paralyzer ring the live run remembered for
        # the cloaker (the direct strategy call does not run the threat scan).
        gained._remembered_paralyzers[Position(7, 15)] = True
        gained._build_grid_index(no_message)
        gained._approved_quest_strategy_key(no_message, [], [])
        self.assertIn((243, 7, 15), gained._quest_strategy_cleared_targets[34])
        # The confirmed kill releases the ring that blocked torch recovery.
        self.assertNotIn(Position(7, 15), gained._remembered_paralyzers)

        # Control: a non-lethal hit also earns experience in proportion to its
        # damage (well under half the kill share); a vanished target with only
        # that gain is not a kill. DECLARED CONSTRUCTED: +4 experience.
        grazed = self.policy()
        grazed._monrace_knowledge[243] = replace(
            grazed._monrace_knowledge[243], level=13, experience=30)
        hit = self.board_from_opening("first_torch_hit", policy=grazed)
        grazed._build_grid_index(hit)
        grazed._approved_quest_strategy_key(hit, hit.visible_monsters, [])
        graze = replace(no_message, player=replace(
            no_message.player, exp=hit.player.exp + 4,
            level=hit.player.level, max_level=hit.player.max_level))
        grazed._build_grid_index(graze)
        grazed._approved_quest_strategy_key(graze, [], [])
        self.assertNotIn((243, 7, 15), grazed._quest_strategy_cleared_targets.get(34, set()))

        # Control: no defeat message and no experience gain stay uncleared.
        # DECLARED CONSTRUCTED: experience held at the pre-throw value.
        silent = self.policy()
        hit = self.board_from_opening("first_torch_hit", policy=silent)
        silent._build_grid_index(hit)
        silent._approved_quest_strategy_key(hit, hit.visible_monsters, [])
        quiet = replace(no_message, player=replace(no_message.player, exp=hit.player.exp))
        target = Position(7, 15)
        dark = replace(quiet, grids={
            **quiet.grids,
            target: replace(quiet.grid_at(target), in_view=False, map_lighting=2),
        })
        silent._build_grid_index(dark)
        self.assertEqual(silent._approved_quest_strategy_key(dark, [], []), WAIT_KEY)
        self.assertNotIn((243, 7, 15), silent._quest_strategy_cleared_targets.get(34, set()))
        self.assertEqual(silent.last_reason, "quest:blocked:fixed-target-not-visible")
        self.assertIn(silent.last_reason, POLICY_FINAL_STOP_REASONS)
        self.assertNotIn(34, silent._quest_strategy_pending_recovery)

    def board_from_opening(self, name, policy=None):
        policy = policy or self.policy()
        return parse_snapshot(
            self.opening_rows["states"][name], policy._monrace_knowledge
        )


if __name__ == "__main__":
    unittest.main()
