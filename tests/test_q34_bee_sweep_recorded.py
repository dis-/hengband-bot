"""D7: captured Q34 boards through choose_key and the production executor.

Only the cleared-target/survey certificates are restored from the checkpoint.
Counterfactual movement and stuck-door replies below are explicitly constructed;
they are not a claim that a new live-game run has completed the quest.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import json
from pathlib import Path
import unittest

from hengbot.cli import _ExecutorInputPort, SendResult
from hengbot.model import Position, parse_snapshot
from hengbot.policy_constants import DOOR_OPEN_LIMIT
from tests.test_input_executor import FaithfulHookGame, ProductionHarness, command_screen
from tests.test_q34_collect_recorded import captured, make_policy


class Q34BeeSweepRecordedTest(ProductionHarness):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((Path(__file__).parent / "fixtures" /
                               "q34-bee-sweep-1029.json").read_text(encoding="utf-8"))
        cls.facts = captured()

    def policy(self, raw):
        policy = make_policy(self.facts)
        board = parse_snapshot(raw, policy._monrace_knowledge)
        policy.prime(board)
        policy._quest_strategy_cleared_targets[34] = {
            (243, 7, 15), (107, 9, 11), (107, 11, 9),
        }
        policy._quest_strategy_surveyed_placements[34] = {
            Position(*cell) for cell in self.data["surveyed"]
        }
        return policy

    def post(self, policy, raw, following):
        # Supply omitted skill knowledge at each boundary, including the
        # constructed transition between captures with different player levels.
        policy.consume_skill_knowledge({
            "player": {"level": raw["player"]["level"]},
            "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
        })
        key = policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge))
        if str(key).startswith("o"):
            # All open attempts in this test world fail, including the old
            # code's o8 against the incident's permanently stuck glass door.
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
        self.assertFalse(game.term_fifo)
        return str(key)

    def test_captured_board_avoids_glass_door_and_engages_bee(self):
        raw = copy.deepcopy(self.data["board"])
        policy = self.policy(raw)
        # Constructed reply: eastward movement reveals the adjacent bee in the
        # separately captured upper-room board. Keep time increasing.
        following = copy.deepcopy(self.data["adjacent_bee"])
        following["turn"] = raw["turn"] + 10
        self.assertEqual(self.post(policy, raw, following), "6")
        self.assertEqual(policy.last_reason, "quest-strategy:placement-sweep")
        self.assertEqual(self.post(policy, following,
                                   dict(following, turn=following["turn"] + 10)), "6")
        self.assertEqual(policy.last_reason, "quest-strategy:melee")

    def test_failed_door_is_abandoned_after_existing_open_bound(self):
        raw = copy.deepcopy(self.data["board"])
        # Constructed closed glass door east of the player. The transport
        # returns unchanged terrain for each unsuccessful opening attempt.
        raw["grid_map"]["runs"].append([3, 15, 1, 4])
        raw["messages"] = ["You failed to pick the lock."]
        policy = self.policy(raw)
        for _ in range(DOOR_OPEN_LIMIT):
            following = dict(raw, turn=raw["turn"] + 10)
            self.assertEqual(self.post(policy, raw, following), "o6")
            raw = following
        key = self.post(policy, raw, dict(raw, turn=raw["turn"] + 10))
        self.assertNotIn(key, ("o6", "o8"))
        self.assertIn((3, 15), policy._blocked_doors)

    def test_captured_bee_in_lower_room_is_pursued(self):
        raw = self.data["escaped_bee"]
        policy = self.policy(raw)
        key = self.post(policy, raw, dict(raw, turn=raw["turn"] + 10))
        self.assertEqual(key, "4")
        self.assertEqual(policy.last_reason, "quest-strategy:approach-final-target")

    def test_sweep_stops_when_failed_doors_seal_its_route(self):
        raw = copy.deepcopy(self.data["board"])
        for y, x in ((3, 13), (3, 15), (4, 14)):
            raw["grid_map"]["runs"].append([y, x, 1, 4])
        policy = self.policy(raw)
        # Constructed previous failed openings: all allowed exits are exhausted.
        policy._blocked_doors.update({(3, 13), (3, 15), (4, 14)})
        self.assertEqual(self.post(policy, raw, dict(raw, turn=raw["turn"] + 10)), "5")
        self.assertEqual(policy.last_reason, "quest:blocked:placement-sweep-route")


if __name__ == "__main__":
    unittest.main()
