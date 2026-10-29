"""D19: recorded n1-c fundraising return that wandered beside a closed door.

Boards, following boards and decision rows are recorded (Yeek cave 1F,
2026-10-30 07:2x; tests/fixtures/fundraise-upstairs-door-20261030.json.gz,
see tests/extract_fundraise_upstairs_door.py).  The remembered terrain and
the exploration fields come from the policy checkpoint written at 07:26:48.

DECLARED CONSTRUCTED: the checkpoint does not carry ``_blocked_doors`` or
``_door_attempts``.  Door [11,160] is restored as given up after
DOOR_OPEN_LIMIT picks: on the recorded terrain it is the only frontier, so
the recorded "no frontier, wander" decisions mean it had been given up
(``test_given_up_door_was_the_only_frontier`` pins that).  Replies to an
open key keep the board unchanged at the next turn (the lock holds).
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
import unittest

from hengbot.cli import _ExecutorInputPort, SendResult, _cell_loop_guard_applies
from hengbot.model import Position, parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_fundraising import (
    FundraisingPurpose, FundraisingPurposeRecord, FundraisingTransportChild,
)
from hengbot.policy_constants import (
    DOOR_OPEN_LIMIT,
    FUNDRAISING_UPSTAIRS_DOOR_ATTEMPT_LIMIT,
)
from tests import test_input_executor as harness
from tests.test_input_executor import FaithfulHookGame, command_screen

FIXTURE = Path(__file__).parent / "fixtures" / "fundraise-upstairs-door-20261030.json.gz"
DOOR = Position(11, 160)
UPSTAIRS = Position(18, 144)


class FundraiseUpstairsDoorRecordedTest(harness.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.data = json.load(stream)

    def case(self, sequence):
        return copy.deepcopy(self.data["boards"][str(sequence)])

    def policy(self, raw):
        policy = HengbotPolicy(monrace_knowledge={})
        policy.prime(parse_snapshot(raw, {}))
        terrain = self.data["terrain"]
        for name in ("known", "marked", "floor", "wall", "door", "rubble"):
            getattr(policy, f"_remembered_{name}_t").update(
                tuple(cell) for cell in terrain[f"{name}_t"])
        policy._remembered_upstairs.update(Position(*cell) for cell in terrain["upstairs"])
        policy._remembered_downstairs.update(Position(*cell) for cell in terrain["downstairs"])
        state = self.data["state"]
        policy._probed_frontiers.update(Position(*cell) for cell in state["_probed_frontiers"])
        for row in state["_visit_counts"]:
            policy._visit_counts[Position(*row["key"])] = row["count"]
        policy._engagement_avoid_cells.update(
            Position(*cell) for cell in state["_engagement_avoid_cells"])
        for name, value in self.data["modes"].items():
            setattr(policy, name, value)
        recorded = self.data["purpose"]
        purpose = FundraisingPurpose(recorded["id"], recorded["mode"],
                                     recorded["first_run_food_waiver"])
        child = recorded["child"]
        policy._fundraising_run_purpose = purpose
        policy._fundraising_purpose_record = FundraisingPurposeRecord(
            purpose, status=recorded["status"],
            child=FundraisingTransportChild(
                purpose.identity, child["direction"], (0, 0, 0),
                child["posted_sequence"], state=child["state"]),
        )
        # DECLARED CONSTRUCTED (module docstring): the door was given up.
        policy._door_attempts[(DOOR.y, DOOR.x)] = DOOR_OPEN_LIMIT
        policy._blocked_doors.add((DOOR.y, DOOR.x))
        return policy

    @staticmethod
    def choose(policy, raw):
        # Supply the skill knowledge the captured process already held, so
        # the periodic skill-experience request does not own the decision.
        policy.consume_skill_knowledge({
            "player": {"level": raw["player"]["level"]},
            "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
        })
        return policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge))

    def post(self, policy, raw, following):
        key = self.choose(policy, raw)
        if str(key).startswith("o"):
            following = dict(raw, turn=following["turn"])
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        game.screens = [command_screen(following["turn"])]
        game.states = [copy.deepcopy(following)]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                            "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual("".join(game.accepted), str(key))
        return str(key)

    def test_recorded_rows_wander_with_a_known_up_staircase(self):
        for sequence in (9220, 9409):
            decision = self.case(sequence)["decision"]
            self.assertEqual(decision["reason"], "fundraise:seek-upstairs-wander")
            self.assertEqual(decision["map_memory"]["up_stairs"], [[18, 144]])
            self.assertEqual(decision["fundraising"]["mode"], "mine")
        self.assertEqual(self.case(9220)["decision"]["key"], "6")
        # n1-c carried no Word of Recall: no recall fallback could end it.
        board = parse_snapshot(self.case(9409)["board"], {})
        self.assertFalse(any(item.is_recall_scroll for item in board.inventory))

    def test_given_up_door_was_the_only_frontier(self):
        raw = self.case(9409)["board"]
        policy = self.policy(raw)
        board = policy._with_grid_memory(parse_snapshot(raw, {}))
        policy._build_grid_index(board)
        self.assertIsNone(policy._nearest_goal_step(board, policy._is_upstairs_target))
        self.assertEqual(policy._plan_explore_path(board), [])
        policy._blocked_doors.clear()
        policy._build_grid_index(board)
        self.assertEqual(policy._plan_explore_path(board)[-1], DOOR)

    def test_beside_the_door_the_return_picks_it_instead_of_wandering(self):
        case = self.case(9220)
        raw = case["board"]
        self.assertEqual(parse_snapshot(raw, {}).player.position, Position(11, 161))
        policy = self.policy(raw)
        key = self.post(policy, raw, case["following"])
        self.assertEqual(key, "o4")
        self.assertEqual(policy.last_reason, "fundraise:open-upstairs-door")
        self.assertEqual(policy._fundraising_upstairs_door_attempts[(DOOR.y, DOOR.x)], 1)
        # Repeated picks hold the cell; the CLI cell guard must not count them.
        board = parse_snapshot(raw, {})
        self.assertFalse(_cell_loop_guard_applies(board, policy.last_reason))

        # The lock holds well past the old limit and past the oscillation
        # window; the return keeps picking the same door.
        following = dict(raw, turn=raw["turn"] + 10)
        for _ in range(DOOR_OPEN_LIMIT + 12):
            raw, following = following, dict(following, turn=following["turn"] + 10)
            self.assertEqual(self.post(policy, raw, following), "o4")
            self.assertEqual(policy.last_reason, "fundraise:open-upstairs-door")

    def test_door_picks_are_bounded(self):
        raw = self.case(9220)["board"]
        policy = self.policy(raw)
        # DECLARED CONSTRUCTED: the lock never yields; jump to the bound.
        policy._fundraising_upstairs_door_attempts[(DOOR.y, DOOR.x)] = (
            FUNDRAISING_UPSTAIRS_DOOR_ATTEMPT_LIMIT)
        key = self.choose(policy, raw)
        self.assertFalse(key.startswith("o"))
        self.assertEqual(policy.last_reason, "fundraise:seek-upstairs-wander")

    def test_far_from_the_door_the_return_walks_toward_it(self):
        case = self.case(9409)
        raw = case["board"]
        self.assertEqual(parse_snapshot(raw, {}).player.position, Position(5, 185))
        policy = self.policy(raw)
        key = self.post(policy, raw, case["following"])
        self.assertEqual(policy.last_reason, "fundraise:seek-upstairs-door")
        self.assertEqual(policy.decision_claim["goal"]["cell"], [11, 161])
        board = policy._with_grid_memory(parse_snapshot(raw, {}))
        door, approach = policy._upstairs_door_route(board)
        self.assertEqual(door, DOOR)
        self.assertEqual(approach[-1], Position(11, 161))
        self.assertEqual(key, policy._direction_key(board.player.position, approach[0]))


if __name__ == "__main__":
    unittest.main()
