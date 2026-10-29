"""D8: recorded Q34 Magic-Eater stops after the three fixed targets died.

Boards and decision rows are recorded (tests/fixtures/q34-final-room-1029.json.gz,
see its provenance).  Restored state is limited to the cleared-target set and,
for the third stop, the survey set reproduced by replaying the recorded boards.
Replies to posted keys are constructed (unchanged board, later turn, or the
next recorded board); they are not a claim of a new live-game run.
"""
import tests  # noqa: F401 -- isolate live runtime files

from collections import deque
import copy
import gzip
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from hengbot.cli import LOOP_WINDOW, _cell_loop_guard_applies, _is_looping, _policy_final_stop_required
from hengbot.model import Position, parse_snapshot
from hengbot.policy_constants import POLICY_FINAL_STOP_REASONS, Q34_FINAL_DOOR_ATTEMPT_LIMIT, WAIT_KEY
from hengbot.quest_final_room import avoided_doors, door_gates, final_search_area
from tests import test_q34_bee_sweep_recorded as bee
from tests.test_input_executor import ProductionHarness
from tests.test_q34_collect_recorded import captured, make_policy

FIXTURE = Path(__file__).parent / "fixtures" / "q34-final-room-1029.json.gz"
JAMMED_TOP = {Position(2, x) for x in range(13, 19)}


def guard_stop_turn(rows):
    """Feed one bot process's recorded decisions through the driver's cell guard."""
    recent = deque(maxlen=LOOP_WINDOW)
    previous = None
    for row in rows:
        if row["reason"] == "loop-detected":
            continue
        position = Position(row["position"]["y"], row["position"]["x"])
        floor = row["floor"]
        snapshot = SimpleNamespace(
            in_town=floor["dungeon_id"] == 0 and floor["level"] == 0 and floor["quest_id"] == 0,
            floor_key=(floor["dungeon_id"], floor["level"], floor["quest_id"]),
            player=SimpleNamespace(position=position),
        )
        if _cell_loop_guard_applies(snapshot, row["reason"], previous):
            recent.append((snapshot.floor_key, position.y, position.x))
            if _is_looping(recent):
                return row["turn"]
        else:
            recent.clear()
        previous = position
    return None


class Q34FinalRoomRecordedTest(ProductionHarness):
    post = bee.Q34BeeSweepRecordedTest.post

    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.data = json.load(stream)
        cls.facts = captured()

    def board(self, turn):
        return copy.deepcopy(self.data["boards"][str(turn)])

    def policy(self, raw, surveyed=()):
        policy = make_policy(self.facts)
        policy.prime(parse_snapshot(raw, policy._monrace_knowledge))
        policy._quest_strategy_cleared_targets[34] = {
            (243, 7, 15), (107, 9, 11), (107, 11, 9),
        }
        policy._quest_strategy_surveyed_placements[34] = {
            Position(*cell) for cell in surveyed
        }
        return policy

    def test_stop1_final_door_lock_picks_are_progress_and_bounded(self):
        rows = self.data["segments"]["final_door_picks"]
        self.assertEqual(rows[-1]["reason"], "loop-detected")
        self.assertEqual(rows[-1]["turn"], 78509)
        # Real loop-detection path: the recorded run stopped on these picks.
        self.assertIsNone(guard_stop_turn(rows))

        raw = self.board(78509)
        policy = self.policy(raw)
        board = parse_snapshot(raw, policy._monrace_knowledge)
        self.assertEqual(board.player.position, Position(5, 14))
        self.assertTrue(board.grid_at(Position(4, 14)).is_closed_door)
        self.assertIn(Position(4, 14), door_gates(board, policy.approved_quest_strategy(34).engagement_plan))
        following = dict(raw, turn=raw["turn"] + 10)
        self.assertEqual(self.post(policy, raw, following), "o8")
        self.assertEqual(policy.last_reason, "quest-strategy:open-final-door")
        self.assertEqual(policy._q34_final_door_attempts, 1)
        # DECLARED CONSTRUCTED: the lock never yields; jump to the bound.
        policy._q34_final_door_attempts = Q34_FINAL_DOOR_ATTEMPT_LIMIT
        key = policy.choose_key(parse_snapshot(following, policy._monrace_knowledge))
        self.assertEqual((key, policy.last_reason), (WAIT_KEY, "quest:blocked:q34-final-door-locked"))
        self.assertIn(policy.last_reason, POLICY_FINAL_STOP_REASONS)
        self.assertTrue(_policy_final_stop_required(policy))

    def test_stop2_opened_door_sweep_is_not_judged_by_earlier_picks(self):
        rows = self.data["segments"]["door_opened_sweep"]
        self.assertEqual(rows[-1]["turn"], 79317)
        self.assertEqual(
            [row["reason"] for row in rows[-5:-1]],
            ["quest-strategy:final-source-cleared"] + ["quest-strategy:placement-sweep"] * 3,
        )
        self.assertIsNone(guard_stop_turn(rows))

        raw = self.board(79296)
        policy = self.policy(raw, surveyed=[(3, 13)])
        self.assertEqual(self.post(policy, raw, self.board(79296) | {"turn": 79308}), "4")
        self.assertEqual(policy.last_reason, "quest-strategy:placement-sweep")
        goal = Position(*policy.decision_claim["goal"]["cell"])
        plan = policy.approved_quest_strategy(34).engagement_plan
        area = final_search_area(policy._quest_knowledge[34].battlefield.terrain, plan)
        self.assertIn(goal, area)

    def test_stop3_bee_seen_through_glass_is_approached_via_final_door(self):
        seen = self.board(80594)
        policy = self.policy(seen, surveyed=self.data["surveyed_80594"])
        self.assertEqual([(m["y"], m["x"]) for m in seen["visible_monsters"]], [(3, 13)])
        self.assertEqual(self.post(policy, seen, self.board(80603)), "4")
        self.assertEqual(policy.last_reason, "quest-strategy:approach-final-target")
        # Recorded next board: the bee is out of sight from [1,12].  The old
        # sweep turned back east ("6") towards the outer corridor.
        lost = self.board(80603)
        self.assertEqual(lost["visible_monsters"], [])
        following = dict(lost, turn=lost["turn"] + 10)
        key = self.post(policy, lost, following)
        self.assertNotEqual(key, "6")
        self.assertEqual(policy.last_reason, "quest-strategy:approach-final-target")
        self.assertEqual(policy.decision_claim["goal"]["cell"], [3, 13])

        board = parse_snapshot(lost, {})
        plan = policy.approved_quest_strategy(34).engagement_plan
        navigator = policy._quest_navigators[34]
        path = navigator._static_path(board.player.position, {Position(3, 13)},
                                      blocked=door_gates(board, plan))
        self.assertIn(Position(4, 14), path)
        self.assertFalse(JAMMED_TOP & set(path))

    def test_stop3_sweep_without_memory_stays_inside_the_rooms(self):
        lost = self.board(80603)
        policy = self.policy(lost, surveyed=self.data["surveyed_80594"])
        key = self.post(policy, lost, dict(lost, turn=lost["turn"] + 10))
        self.assertNotEqual(key, "6")
        self.assertEqual(policy.last_reason, "quest-strategy:placement-sweep")
        plan = policy.approved_quest_strategy(34).engagement_plan
        area = final_search_area(policy._quest_knowledge[34].battlefield.terrain, plan)
        self.assertIn(Position(*policy.decision_claim["goal"]["cell"]), area)
        self.assertNotIn(Position(1, 15), area)
        # The approved final door is the only avoided-list exception.
        self.assertNotIn(Position(4, 14), avoided_doors(plan))
        self.assertTrue({Position(4, x) for x in (15, 16, 17)} <= avoided_doors(plan))


if __name__ == "__main__":
    unittest.main()
