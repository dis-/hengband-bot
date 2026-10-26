"""Issue #47: saved Lv5 churn boundaries, real chooser and follow executor.

The resume latch/claim is reconstructed from the recorded active Reach claim.
Movement replies and a later completed-quest reply are explicitly constructed;
these tests do not claim a fresh-character game run.
"""
import tests  # noqa: F401

import copy
import gzip
import json
import io
import time
from pathlib import Path
import unittest

from hengbot.claim_register import ClaimOwner, reach
from hengbot.model import Position, parse_snapshot
from hengbot.cli import PostingContract, _ExecutorInputPort, _send_decision_key_with_prompt_chain
import tests.test_input_executor as executor_harness
from tests.test_input_executor import FaithfulHookGame, command_screen, prompt_screen
from tests import test_q34_collect_recorded as collect_tests

FIXTURE = Path(__file__).with_name("fixtures") / "q34-churn-20261026.json.gz"


class Q34ChurnRecordedTest(executor_harness.ProductionHarness):
    def post(self, policy, raw, key, following):
        """Production follow executor with captured monster knowledge."""
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        screens = []
        expected = [key]
        if key.startswith(("D", "o")) and len(key) == 2 and policy.last_reason.startswith("chest:"):
            expected = [key[0], key[1]]
            screens.append(prompt_screen("Direction (Escape to cancel)?"))
        game.screens = screens + [command_screen(following["turn"])]
        game.states = [copy.deepcopy(raw) for _ in screens] + [copy.deepcopy(following)]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 10).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _, _, _ = _send_decision_key_with_prompt_chain(
            port, "q34-churn-replay", key, None, set(), policy=policy,
            shadow_client=None, file=io.StringIO(), deadline=time.monotonic() + 10,
            poll_interval=0, prompt_japanese=False,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=parse_snapshot(raw, policy._monrace_knowledge),
            posting_contract=PostingContract(), in_store=False)
        self.assertTrue(sent, getattr(port.last_result, "reason", None))
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual(game.accepted, expected)
        self.assertFalse(game.term_fifo)

    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.captures = json.load(stream)["captures"]
        cls.quest_data = collect_tests.captured()

    def boundary(self, capture):
        policy = collect_tests.make_policy(self.quest_data)
        rows = capture["rows"]
        policy.consume_skill_knowledge(next(
            row for row in reversed(rows)
            if row["type"] == "knowledge"
            and row["knowledge"]["category"] == "skill_exp"
        ))
        raw = copy.deepcopy(next(
            row for row in reversed(rows) if row["type"] == "player_turn"
        ))
        return policy, raw

    def test_historical_window_identifies_four_cell_competing_owners(self):
        capture = self.captures[1]
        window = capture["window"]
        self.assertEqual(len(window), 40)
        self.assertEqual({tuple(row["position"].values()) for row in window},
                         {(5, 13), (5, 14), (5, 15), (6, 15)})
        self.assertEqual(sum(row["reason"] == "chest:approach" for row in window), 19)
        self.assertEqual(sum(row["reason"] == "quest-strategy:survey-throw-point"
                             for row in window), 20)
        for row in window:
            if row["reason"] == "chest:approach":
                self.assertEqual(row["claim"]["goal"]["cell"], [4, 14])
                self.assertEqual(row["claim"]["owner"], "floor-loot")
                self.assertEqual(row["player"]["level"], 5)

    def test_unfinished_quest_does_not_start_chest_or_health_wait(self):
        for capture in self.captures:
            with self.subTest(life=capture["life"]):
                policy, raw = self.boundary(capture)
                board = parse_snapshot(raw, policy._monrace_knowledge)
                self.assertEqual(board.quests[34].status, 1)
                self.assertFalse(board.visible_monsters)
                self.assertIn([3, 14, 1, 7], raw["grid_map"]["found_items"])
                # The first capture is below the health gate; the last is full.
                self.assertEqual(board.player.hp < board.player.max_hp * 0.8,
                                 capture["life"] == "life-017")
                key = str(policy.choose_key(board))
                self.assertEqual((key, policy.last_reason),
                                 ("2", "quest-strategy:survey-throw-point"))
                self.assertIsNone(policy._chest_position)
                following = copy.deepcopy(raw)
                following["player"]["y"] += 1
                following["turn"] += 10
                self.post(policy, raw, key, following)

    def test_resumed_chest_is_closed_by_name_and_throw_survey_progresses(self):
        for capture in self.captures:
            with self.subTest(life=capture["life"]):
                policy, raw = self.boundary(capture)
                # DECLARED CONSTRUCTED: rebuild the in-flight chest latch and
                # Reach shown by the incident decision tail (not serialized in
                # policy-state.json). Other observations remain recorded.
                policy._observe(policy._with_grid_memory(
                    parse_snapshot(raw, policy._monrace_knowledge)))
                policy._chest_position = Position(3, 14)
                policy._chest_phase_counts = {"search": 1}
                policy._chest_preopen_objects = {Position(3, 14): (1, 0)}
                policy._chest_collecting = True
                policy._claim_register.declare(
                    ClaimOwner.FLOOR_LOOT, reach((4, 14)),
                    floor=(0, 5, 34), rank=48, rung="_chest_processing_key#1",
                )
                positions = []
                for index in range(3):
                    before = copy.deepcopy(raw)
                    key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
                    if index == 0:
                        closed = policy.decision_claim["closed_claim"]
                        self.assertEqual(closed["closed"], "release")
                        self.assertEqual(closed["closed_reason"], "chest-deferred-quest-incomplete")
                        self.assertIsNone(policy._chest_position)
                        self.assertEqual(policy._chest_phase_counts, {})
                        self.assertIsNone(policy._chest_preopen_objects)
                        self.assertFalse(policy._chest_collecting)
                        self.assertNotIn(Position(3, 14), policy._processed_chest_positions)
                    positions.append((raw["player"]["y"], raw["player"]["x"]))
                    self.assertTrue(policy.last_reason.startswith("quest-strategy:"), policy.last_reason)
                    # DECLARED CONSTRUCTED: apply policy movement on the source
                    # floor. At the stand the captured empty cloaker cell is
                    # confirmed and EXECUTE advances its target/recovery state.
                    if key == "2":
                        raw["player"]["y"] += 1
                    else:
                        self.assertEqual(policy.last_reason, "quest-strategy:survey-target-cleared")
                    raw["turn"] += 10
                    self.post(policy, before, key, raw)
                    policy.confirm_key_posted(key)
                self.assertEqual(positions, [(5, 13), (6, 13), (7, 13)])
                self.assertIn((243, 7, 15), policy._quest_strategy_cleared_targets[34])

    def test_completed_churn_floor_still_opens_chest_in_place(self):
        policy, raw = self.boundary(self.captures[1])
        # DECLARED CONSTRUCTED: a later game reply confirms quest completion,
        # recovery and standing at the final door beside the recorded chest.
        # Trap outcomes/content generation are not captured; verify posted open.
        raw["progress"]["quests"][0]["status"] = 2
        raw["player"]["hp"] = raw["player"]["max_hp"]
        raw["player"]["y"], raw["player"]["x"] = 4, 14
        reasons = []
        for _ in range(10):
            before = copy.deepcopy(raw)
            key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
            reasons.append(policy.last_reason)
            self.assertEqual(policy._chest_position, Position(3, 15))
            self.assertFalse(key.startswith("g"), "keep the chest on the floor")
            raw["turn"] += 10
            self.post(policy, before, key, raw)
            policy.confirm_key_posted(key)
            if policy.last_reason == "chest:open":
                self.assertEqual(key, "o9")
                break
        self.assertEqual(reasons, ["chest:search"] * 6 + ["chest:disarm"] * 2 + ["chest:open"])


if __name__ == "__main__":
    unittest.main()
