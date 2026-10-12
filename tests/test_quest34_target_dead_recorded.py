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
        # DECLARED CONSTRUCTED: the same empty cell is now outside the
        # lantern's one-cell radius, so its sub-kill-share experience cannot
        # be mistaken for the new geometric empty-cell proof.
        graze = replace(no_message, player=replace(
            no_message.player, exp=hit.player.exp + 4,
            level=hit.player.level, max_level=hit.player.max_level),
            light_radius=1)
        grazed._build_grid_index(graze)
        grazed._approved_quest_strategy_key(graze, [], [])
        self.assertNotIn((243, 7, 15), grazed._quest_strategy_cleared_targets.get(34, set()))

        # The recorded board also pins restart reconstruction when both kill
        # evidence channels were missed: own-grid vision, range, and LOS show
        # the target cell is empty even though canonical lighting is dark.
        # DECLARED CONSTRUCTED: restart has no prior visible-target or throw
        # record, and the defeat line is omitted from this recorded board.
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
        self.assertEqual(silent._approved_quest_strategy_key(dark, [], []), "6")
        self.assertIn((243, 7, 15), silent._quest_strategy_cleared_targets[34])
        self.assertEqual(
            silent.last_reason,
            "quest-strategy:recover-defeated-target-torches",
        )
        self.assertIn(34, silent._quest_strategy_pending_recovery)

        # Geometry controls use the same restart survey with one fact removed.
        for control_name, control in (
            ("outside-light", replace(dark, light_radius=1)),
            (
                "behind-wall",
                replace(
                    dark,
                    grids={
                        **dark.grids,
                        Position(7, 14): replace(
                            dark.grid_at(Position(7, 14)), allows_los=False
                        ),
                    },
                ),
            ),
        ):
            blocked = self.policy()
            blocked._build_grid_index(control)
            blocked._approved_quest_strategy_key(control, [], [])
            self.assertNotIn(
                (243, 7, 15),
                blocked._quest_strategy_cleared_targets.get(34, set()),
                control_name,
            )

        invisible_target = self.policy()
        race = invisible_target._monrace_knowledge[243]
        invisible_target._monrace_knowledge[243] = replace(
            race, flags=frozenset(set(race.flags) | {"INVISIBLE"})
        )
        invisible_target._build_grid_index(dark)
        invisible_target._approved_quest_strategy_key(dark, [], [])
        self.assertNotIn(
            (243, 7, 15),
            invisible_target._quest_strategy_cleared_targets.get(34, set()),
        )

    def test_protocol3_geometry_retires_paralyzer_memory_and_reconstructs_lane(self):
        # Pin the fallback to the recorded protocol-3 Q34 board: the cloaker
        # cell and all known grids use canonical lighting symbols, while the
        # player's light and open LOS give current visibility.
        target = Position(7, 15)
        board = self.board_from_opening("cloaker_killed")
        self.assertTrue(board.can_see_own_grid)
        self.assertFalse(board.grids[target].in_view)

        policy = self.policy()
        policy._remembered_paralyzers[target] = (False, 243)
        policy._refresh_paralyzer_avoidance(board, [])
        self.assertNotIn(target, policy._remembered_paralyzers)

        # Controls: geometry cannot clear a remembered invisible race, a cell
        # beyond the player's light, or one hidden behind a known wall.
        invisible = self.policy()
        race = invisible._monrace_knowledge[243]
        invisible._monrace_knowledge[243] = replace(
            race, flags=frozenset(set(race.flags) | {"INVISIBLE"})
        )
        invisible._remembered_paralyzers[target] = (False, 243)
        invisible._refresh_paralyzer_avoidance(board, [])
        self.assertIn(target, invisible._remembered_paralyzers)

        outside_board = replace(board, light_radius=1)
        outside = self.policy()
        outside._remembered_paralyzers[target] = (False, 243)
        outside._refresh_paralyzer_avoidance(outside_board, [])
        self.assertIn(target, outside._remembered_paralyzers)

        wall_grids = dict(board.grids)
        between = Position(7, 14)
        wall_grids[between] = replace(wall_grids[between], allows_los=False)
        behind_wall_board = replace(board, grids=wall_grids)
        behind_wall = self.policy()
        behind_wall._remembered_paralyzers[target] = (False, 243)
        behind_wall._refresh_paralyzer_avoidance(behind_wall_board, [])
        self.assertIn(target, behind_wall._remembered_paralyzers)

        # DECLARED CONSTRUCTED from the recorded Q34 board: moving the player
        # to the centre of the approved recovery lane and removing the torch
        # substrate makes all five lane cells lie within light radius 2.
        lane_policy = self.policy()
        lane_cells = [Position(7, x) for x in range(14, 19)]
        lane_grids = dict(board.grids)
        for cell in lane_cells:
            self.assertIn(cell, lane_grids)
            lane_grids[cell] = replace(
                lane_grids[cell], object_count=0, object_tvals=(),
                has_monster=False,
            )
        lane_player = replace(board.player, position=Position(7, 16))
        lane = replace(board, player=lane_player, grids=lane_grids)
        lane_policy._build_grid_index(lane)
        lane_policy._approved_quest_strategy_key(lane, [], [])
        self.assertIn((243, 7, 15), lane_policy._quest_strategy_cleared_targets[34])

        # The same lane remains uncleared when its target race is invisible.
        invisible_lane = self.policy()
        race = invisible_lane._monrace_knowledge[243]
        invisible_lane._monrace_knowledge[243] = replace(
            race, flags=frozenset(set(race.flags) | {"INVISIBLE"})
        )
        invisible_lane._build_grid_index(lane)
        invisible_lane._approved_quest_strategy_key(lane, [], [])
        self.assertNotIn(
            (243, 7, 15),
            invisible_lane._quest_strategy_cleared_targets.get(34, set()),
        )

    def test_non_q34_survey_uses_live_light_geometry(self):
        # DECLARED CONSTRUCTED from the Q31 approved survey plan: its first
        # fixed target is empty and outside CAVE_VIEW, but lies in live light
        # with known, unobstructed LOS from the approved stand.
        quest_tests.ApprovedQuestStrategyExecutionTest.setUpClass()
        case = quest_tests.ApprovedQuestStrategyExecutionTest()
        profile = replace(case.profiles[31], approved=True)
        info = quest_tests.load_quest_knowledge(
            quest_tests.REAL_QUEST_DEFINITIONS
        )[31]
        policy = HengbotPolicy(
            quest_strategies={31: profile},
            quest_knowledge={31: info},
            monrace_knowledge={
                329: quest_tests.MonraceKnowledge(
                    500, 110, False, False,
                    flags=frozenset({"NEVER_MOVE"}),
                )
            },
        )
        stand = Position(18, 1)
        target = Position(16, 3)
        snapshot = quest_tests.Snapshot(
            quest_tests.player(stand.y, stand.x),
            {
                stand: quest_tests.grid(stand.y, stand.x),
                Position(17, 2): quest_tests.grid(17, 2),
                target: quest_tests.grid(target.y, target.x),
            },
            [],
            floor_key=(0, 22, 31),
            can_see_own_grid=True,
            light_radius=3,
        )
        policy._quest_strategy_initial_hold_turns[31] = 60
        policy._build_grid_index(snapshot)
        self.assertEqual(
            policy._approved_quest_strategy_key(snapshot, [], []), WAIT_KEY
        )
        self.assertEqual(policy.last_reason, "quest-strategy:survey-target-cleared")
        self.assertIn((329, target.y, target.x), policy._quest_strategy_cleared_targets[31])

    def board_from_opening(self, name, policy=None):
        policy = policy or self.policy()
        return parse_snapshot(
            self.opening_rows["states"][name], policy._monrace_knowledge
        )


if __name__ == "__main__":
    unittest.main()
