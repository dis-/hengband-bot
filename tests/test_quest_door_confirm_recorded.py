"""#102: a non-entering town step must not land on a quest entrance.

Fixture ``fixtures/quest-door-confirm-20261023.jsonl.gz`` holds the two raw
``player_turn`` boards recorded just before the two keep-running stops of
2026-10-23 15:14:45 and 15:14:52 (quick-start Zombie Warrior, Lv17, town 1,
bot ac203b36): row 0 is turn 498772, row 1 turn 498801, both with the player
at (24,46).  The live decisions on these boards were key ``3`` reason
``town:repetition-depart`` (chain: ``_town_blocked_key`` ->
``_descent_step`` "seek-downstairs" -> ``_step_toward``), which landed on the
quest-2 entrance (25,47) and stopped on the unowned confirm
"クエストに入りますか？[y/n]".  The recorded cell carries both DOWN_STAIRS and
QUEST_ENTER (TerrainDefinitions id 8).

Measured at ac203b36 (this module with the src diff reversed):
  _descent_step on both boards        -> (25,47), last_reason seek-downstairs
  _step_toward(board, (25,47))        -> '3'
  _break_livelock onto (25,47)        -> '3', reason breakout
  _step_toward with (25,47) unemitted -> '3'

Variants built with ``dataclasses.replace`` and the patched collaborators are
DECLARED CONSTRUCTED; every assertion on the recorded boards themselves uses
the boards unchanged.
"""

import tests  # noqa: F401

import ast
import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from hengbot.model import Position, parse_snapshot
from hengbot.policy import LIVELOCK_LIMIT, HengbotPolicy
from hengbot.policy_constants import WAIT_KEY
from hengbot.policy_types import DecisionContext
from hengbot.quest_navigator import QuestFloorNavigator
from hengbot.town_maps import find_outpost_map, find_town_map, parse_town_map


FIXTURE = Path(__file__).parent / "fixtures" / "quest-door-confirm-20261023.jsonl.gz"
SRC = Path(__file__).resolve().parents[1] / "src" / "hengbot"
ENTRANCE = Position(25, 47)
ORIGIN = Position(24, 46)
QUEST_ID = 2


def _town_maps():
    maps = {0: parse_town_map(find_outpost_map(Path(__file__)))}
    for town_index in range(2, 6):
        path = find_town_map(town_index, Path(__file__))
        if path is not None:
            maps[town_index - 1] = parse_town_map(path)
    return maps


class QuestDoorConfirmRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.boards = [parse_snapshot(json.loads(line), {}) for line in stream]
        cls.maps = _town_maps()

    def policy(self, board):
        policy = HengbotPolicy(town_map=self.maps[0], town_maps=self.maps)
        policy._build_grid_index(board)
        return policy

    def test_recorded_boards_stand_next_to_the_quest_entrance(self):
        self.assertEqual(len(self.boards), 2)
        for board in self.boards:
            grid = board.grid_at(ENTRANCE)
            self.assertEqual(board.player.position, ORIGIN)
            self.assertTrue(board.in_town)
            self.assertTrue(grid.has_quest_enter)
            self.assertTrue(grid.has_down_stairs)
            self.assertEqual(grid.quest_id, QUEST_ID)

    def test_departure_no_longer_takes_the_quest_entrance_for_a_downstairs(self):
        # ac203b36: (25,47) / seek-downstairs on both boards.
        for board in self.boards:
            policy = self.policy(board)
            with patch.object(HengbotPolicy, "_descent_is_blocked", return_value=False):
                step = policy._descent_step(board)
            self.assertIsNone(step)
            self.assertIsNone(policy._descent_target_goal)
            self.assertFalse(
                policy._is_descent_target(board, board.grid_at(ENTRANCE))
            )

    def test_non_entering_step_onto_the_entrance_is_refused(self):
        # ac203b36: '3' (the live key that raised the confirm).
        for board in self.boards:
            policy = self.policy(board)
            key = policy._step_toward(board, ENTRANCE)
            self.assertEqual(key, WAIT_KEY)
            self.assertEqual(policy.last_reason, "nav:confirm-cell-avoided")

    def test_unemitted_entrance_falls_back_to_the_town_map(self):
        # DECLARED CONSTRUCTED: the entrance grid removed (an unlit night cell).
        # ac203b36: '3'.
        board = self.boards[0]
        night = replace(
            board,
            grids={pos: grid for pos, grid in board.grids.items() if pos != ENTRANCE},
        )
        policy = self.policy(night)
        self.assertEqual(policy._step_toward(night, ENTRANCE), WAIT_KEY)
        self.assertEqual(policy.last_reason, "nav:confirm-cell-avoided")
        policy.last_reason = "quest:enter:approach"
        self.assertEqual(policy._step_toward(night, ENTRANCE), "3")

    def test_livelock_breakout_does_not_pick_the_entrance(self):
        # DECLARED CONSTRUCTED: the repeat counter is primed and the breakout
        # chooser patched to the entrance.  ac203b36: ('3', 'breakout').
        board = self.boards[0]
        policy = self.policy(board)
        policy.last_reason = "seek-downstairs"
        policy._last_move_key = "6"
        policy._last_move_pos = ORIGIN
        policy._move_repeat = LIVELOCK_LIMIT - 1
        with patch.object(HengbotPolicy, "_breakout_step", return_value=ENTRANCE):
            key = policy._break_livelock(board, "6")
        self.assertEqual(key, "6")
        self.assertEqual(policy.last_reason, "seek-downstairs")

    def test_control_breakout_onto_plain_floor_unchanged(self):
        board = self.boards[0]
        policy = self.policy(board)
        policy.last_reason = "seek-downstairs"
        policy._last_move_key = "6"
        policy._last_move_pos = ORIGIN
        policy._move_repeat = LIVELOCK_LIMIT - 1
        with patch.object(
            HengbotPolicy, "_breakout_step", return_value=Position(25, 46)
        ):
            key = policy._break_livelock(board, "6")
        self.assertEqual((key, policy.last_reason), ("2", "breakout"))

    def test_control_entering_owner_still_steps_onto_its_entrance(self):
        board = self.boards[0]
        for reason in ("quest:enter", "quest:enter:approach", "fixedquest:enter"):
            policy = self.policy(board)
            policy.last_reason = reason
            self.assertEqual(policy._step_toward(board, ENTRANCE), "3")
        # The approach owner that does not bind the entry answer is refused.
        policy = self.policy(board)
        policy.last_reason = "fixedquest:approach"
        self.assertEqual(policy._step_toward(board, ENTRANCE), WAIT_KEY)

    def test_control_quest_enter_approach_enters(self):
        board = self.boards[0]
        with patch.object(
            HengbotPolicy, "_quest_equipment_entry_allowed", return_value=True
        ):
            policy = self.policy(board)
            key = QuestFloorNavigator.enter_from_town(policy, board, QUEST_ID)
            self.assertEqual((key, policy.last_reason), ("3", "quest:enter:approach"))

            policy = self.policy(board)
            policy._decision_context = DecisionContext(
                equipment_transaction_owned=False, identity=1
            )
            key = QuestFloorNavigator.enter_from_town(policy, board, QUEST_ID)
            self.assertEqual(str(key), "3")
            self.assertEqual(policy.last_reason, "quest:enter:approach")

    def test_control_fixed_quest_enter_steps_onto_its_entrance(self):
        board = self.boards[0]
        policy = self.policy(board)
        with patch.object(
            HengbotPolicy, "_quest_equipment_entry_allowed", return_value=True
        ), patch.object(
            HengbotPolicy, "_kill_quest_descent_allowed", return_value=True
        ):
            key = policy._fixed_quest_enter_key(board, QUEST_ID)
        self.assertEqual((key, policy.last_reason), ("3", "fixedquest:enter"))

    def test_control_ordinary_town_step_unchanged(self):
        for board in self.boards:
            policy = self.policy(board)
            self.assertEqual(policy._step_toward(board, Position(24, 47)), "6")
            self.assertEqual(policy._step_toward(board, Position(25, 46)), "2")


# Functions that compose a ``_direction_key`` into a posted key without
# walking onto terrain (an attack into an occupied monster cell, a command
# suffix, a comparison) -- classified in LUNA-DIAG-step-key-unify.txt (#83)
# and LUNA-DIAG-qdoor.txt (#102).
NOT_A_WALK = {
    "_low_hp_no_kit_hit_key": "ALTER_KEY + dir (do_cmd_alter), not a walk",
    "_low_hp_walk_gate": "melee on the weakest adjacent monster",
    "_decide": "flee:cornered-attack / melee on adjacent monsters",
    "_blocking_escape_melee_key": "melee, candidates at distance <= 1",
    "_breakout_step": "comparison against the avoided key",
    "_forbid_wait_while_damaged": "melee / no-wait:attack on monsters",
    "_esp_threat_hunt_key": "melee on an adjacent monster",
    "_ranged_attack_key": "fire suffix",
    "_emergency_item": "cornered attack on an adjacent monster",
    "_melee_swarm_combat_key": "melee on an adjacent monster",
    "_choke_engagement_key": "melee on an adjacent monster",
    "_mining_tunnel_key": "TUNNEL_KEY + dir into a wall",
    "_chest_processing_key": "chest disarm/open direction",
    "_disengage_move_or_escalate": "melee on the weakest adjacent monster",
    "_q2_ranged_core_key": "fire suffix",
    "_q2_phase_key": "Sewer quest floor: melee / no-ammo fallback (no QUEST_ENTER)",
    "_quest_execute_key": "quest floor: melee, throw/open suffixes",
    "_unseen_retreat_intercept_key": "melee on an adjacent monster",
    "_town_kill_mob_key": "'+' + dir + 'y' attack on a town monster",
    "decide": "quest floor melee on an adjacent monster",
}
# Bare town walks that route with the modal-cell avoidance of
# _town_map_goal_route / _nearest_goal_route / the boxed breakout candidate
# filter (policy_town.py, has_quest_enter excluded).  Residual: the routers'
# second attempt may cross a modal cell; recorded in LUNA-REPORT-qdoor.txt.
TOWN_ROUTED_RESIDUAL = {
    "_town_holder_declared_key",
    "_town_holder_wait_key",
    "_boxed_town_breakout_key",
}
STEP_ENTRY = "_step_toward"
PREDICATE = "_step_raises_unintended_confirm"


def direction_key_walkers() -> dict[str, set[str]]:
    """Every function (by module) that composes ``_direction_key(``."""
    found: dict[str, set[str]] = {}
    for path in sorted(SRC.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for function in ast.walk(tree):
            if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            names = {
                node.func.attr
                for node in ast.walk(function)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
            }
            if "_direction_key" in names:
                found.setdefault(function.name, set()).update(names)
    return found


class StepEntryStructureTest(unittest.TestCase):
    def test_every_walking_producer_consults_the_confirm_predicate(self):
        walkers = direction_key_walkers()
        self.assertIn(PREDICATE, walkers[STEP_ENTRY])
        bypass = sorted(
            name
            for name, calls in walkers.items()
            if name != STEP_ENTRY
            and PREDICATE not in calls
            and name not in NOT_A_WALK
            and name not in TOWN_ROUTED_RESIDUAL
        )
        self.assertEqual(bypass, [])
        self.assertIn(PREDICATE, walkers["_break_livelock"])


if __name__ == "__main__":
    unittest.main()
