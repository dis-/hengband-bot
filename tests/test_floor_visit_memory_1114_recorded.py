"""n1-c life-207: a new 60F level read the *Destruction* circles of the earlier 60F levels.

Owner 2026-11-14: 「帰還の条件がおかしい気がする。」 then 「先に調べて直して」.  n1-c life-207
(Magic-Eater Lv46, max HP 603) went from town to ガラスの城 (Glass castle) 60F and back about once
a minute.  Every Word of Recall lands on a new level, but the floor key (20, 60, 0) is the same
for every visit, and memories keyed by the floor key alone survived the town (floor_visit_memory).
area_mapping's held the circles of 26 *Destruction* uses of earlier 60F levels: each new level
read as destroyed around the player from its first board (``me-power:after-destruction:map-area``
on arrival, ``stuck:destroyed-circle-teleport`` on arrival at 04:26:08, the circles' sure radius
read as explored ground before ``stuck:recall-escape`` at 04:05:25 and 04:05:50).

Recorded: tests/fixtures/recall-churn-1114.pkl.xz (tests/extract_recall_churn_1114_fixture.py):
for decisions 4132-4135 (the 60F arrival of 04:26:45 to the first board after the Recall read)
the response lines the live bot read and the policy checkpoint it decided that board from.  Each
pin restores its board's checkpoint and decides through the public ``choose_key``.

DECLARED CONSTRUCTED: the arrival board without its hostiles, each later quiet board ten game
turns on with the previous decision's operation reported complete (the live board after a
posted key carries it); the executor's prompts.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import pickle
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import area_mapping, floor_visit_memory, sealed_pocket
from hengbot.cli import _ExecutorInputPort, SendResult, _consume_response_sequence
from hengbot.latch_onset_capture import restore_checkpoint_bytes
from hengbot.policy import HengbotPolicy
from tests.support import recorded as executor_pins
from tests.test_magic_eater_o3 import prompt
from tests.test_me_device_attacks import power_screen

FIXTURE = Path(__file__).with_name("fixtures") / "recall-churn-1114.pkl.xz"
ARRIVAL, AFTER_RECALL = 4132, 4135
FLOOR = (20, 60, 0)
STALE_MAP = ("mAj", "me-power:after-destruction:map-area")
NEW_FLOOR_MAP = ("mAj", "me-power:new-floor:map-area")
MAP_NAME = "周辺感知"

CASE = pickle.loads(lzma.decompress(FIXTURE.read_bytes()))
SEGMENTS = {segment["decision"]["decision_sequence"]: segment for segment in CASE["segments"]}


def consumed(sequence):
    """(policy, board) of the board read from the live history, not yet decided."""
    policy = restore_checkpoint_bytes(HengbotPolicy, CASE["checkpoints"][sequence])
    with TemporaryDirectory() as scratch:
        _, boards = _consume_response_sequence(
            SEGMENTS[sequence]["lines"], policy, lambda _key: True, policy._monrace_knowledge,
            knowledge_ledger_path=Path(scratch) / "k.jsonl")
    return policy, policy.with_known_skill_exp(boards[-1])


def raw_board(sequence):
    return json.loads(next(line for line in reversed(SEGMENTS[sequence]["lines"])
                           if json.loads(line).get("type") == "player_turn"))


def live(sequence):
    decision = SEGMENTS[sequence]["decision"]
    return decision["key"], decision["reason"]


def quiet_arrival(boards=3):
    """(policy, decisions) of the arrival board without its hostiles and the quiet boards after
    it (DECLARED CONSTRUCTED, module docstring)."""
    policy, board = consumed(ARRIVAL)
    quiet = replace(board, visible_monsters=[], detected_monsters=[], messages=[])
    decided, reason = [], None
    for index in range(boards):
        key = policy.choose_key(replace(
            quiet, turn=quiet.turn + 10 * index, completed_operation_owner=reason,
            completed_operation_sequence=policy._decision_sequence if reason else None))
        decided.append((key, policy.last_reason))
        policy.confirm_key_posted(key)
        reason = policy.last_reason
    return policy, decided


class FloorVisitMemory1114RecordedTest(executor_pins.ProductionHarness):
    def test_recorded_scene(self):
        """The checkpoint before the arrival: in town, with the earlier 60F levels' circles."""
        policy, board = consumed(ARRIVAL)
        self.assertEqual(policy._floor_key, (0, 0, 0))
        self.assertEqual(board.floor_key, FLOOR)
        memory = policy._area_mapping_memory
        self.assertEqual(memory.floor, FLOOR)
        self.assertEqual(len(memory.circles), 26)
        self.assertEqual(getattr(policy, sealed_pocket.TELEPORTED)[0], (FLOOR, 21))
        self.assertEqual(live(ARRIVAL), ("re", "emergency:teleport"))
        self.assertEqual(live(AFTER_RECALL), STALE_MAP)

    def test_the_new_level_reads_no_earlier_visit(self):
        policy, board = consumed(ARRIVAL)
        earlier = {name: copy.deepcopy(getattr(policy, name, None))
                   for name, _, _ in floor_visit_memory.VISIT_MEMORIES}
        policy.choose_key(board)
        self.assertFalse(area_mapping.destroyed_since_arrival(policy, board))
        self.assertFalse(area_mapping.in_destroyed_circle(policy, board, [board.player.position]))
        self.assertIsNone(sealed_pocket.destroyed_leave_key(policy, board))
        carried = [name for name, value in earlier.items()
                   if value and getattr(policy, name, None) == value]
        self.assertEqual(carried, [])
        # The recorded checkpoint held the earlier levels' memories of these.
        self.assertTrue(all(earlier[name] for name in (
            "_area_mapping_memory", "_destroyed_circle_teleport", "_sealed_pocket_memory",
            "_lit_floor_memory", "_loot_frontier_tried", "_summoner_counter_targets")), earlier)

    def test_the_arrival_maps_as_a_new_floor(self):
        """The recorded arrival without its hostiles: detection, traps, then the map of a new
        floor, not the map after a *Destruction* (live 4135, the same power on the stale
        reading)."""
        _, decided = quiet_arrival()
        self.assertEqual(decided[0][1], "me-power:new-floor:detect-all:powerful")
        self.assertEqual(decided[1][1], "me-power:new-floor:detect-traps")
        self.assertEqual(decided[2], NEW_FLOOR_MAP)

    def test_the_map_goes_through_the_executor(self):
        policy, decided = quiet_arrival()
        key = decided[2][0]
        raw = copy.deepcopy(raw_board(ARRIVAL))
        game = executor_pins.FaithfulHookGame()
        game.state = raw
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = [prompt("[A] 杖, [B] 魔法棒, [C] ロッド:"),
                        power_screen("staff", [("j", MAP_NAME, 3, 3, 5)]),
                        executor_pins.command_screen(raw["turn"] + 10)]
        game.states = [dict(raw, turn=raw["turn"] + 10) for _ in game.screens]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                             "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual(game.accepted, ["m", "A", "j"])


if __name__ == "__main__":
    unittest.main()
