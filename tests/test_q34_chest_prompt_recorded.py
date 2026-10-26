"""Issue #47 round 2: recorded at-feet prompt through the follow executor.

Only the open stop screen is recorded. Reusing that screen for disarm is a
source-derived reply: both commands call get_rep_dir(player, true). Command
boundaries, successful answers and easy-direction replies are constructed;
this replay does not claim a fresh-character game run.
"""
import tests  # noqa: F401

import copy
import gzip
import io
import json
from pathlib import Path
import time

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_decision_key_with_prompt_chain
from hengbot.input_executor import ScreenKind, classify_screen
from hengbot.model import Position, parse_snapshot
import tests.test_input_executor as executor_harness
from tests.test_input_executor import FaithfulHookGame, command_screen
from tests.test_q34_collect_recorded import captured, make_policy

FIXTURE = Path(__file__).with_name("fixtures") / "q34-chest-prompt-20261026.json.gz"


class Q34ChestPromptRecordedTest(executor_harness.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.captures = json.load(stream)["captures"]
        cls.quest_data = captured()

    def policy(self, capture):
        policy = make_policy(self.quest_data)
        policy.consume_skill_knowledge(capture["skill"])
        return policy

    def post(self, policy, raw, key, screen, *, automatic=False):
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        following = copy.deepcopy(raw)
        # DECLARED CONSTRUCTED: successful command response at a new stable
        # boundary; no generated chest contents or trap outcome is asserted.
        following["turn"] += 10
        prompted = len(key) == 2 and key[0] in "Do" and not automatic
        game.screens = ([copy.deepcopy(screen)] if prompted else []) + [command_screen(following["turn"])]
        prompt_state = copy.deepcopy(raw)
        prompt_state["input_context"] = copy.deepcopy(screen["input_context"])
        game.states = ([prompt_state] if prompted else []) + [following]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 10).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _, _, _ = _send_decision_key_with_prompt_chain(
            port, "q34-chest-prompt-replay", key, None, set(), policy=policy,
            shadow_client=None, file=io.StringIO(), deadline=time.monotonic() + 10,
            poll_interval=0, prompt_japanese=True,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=parse_snapshot(raw, policy._monrace_knowledge),
            posting_contract=PostingContract(), in_store=False)
        self.assertTrue(sent, getattr(port.last_result, "reason", None))
        self.assertEqual(port.last_result.outcome, "completed")
        expected = [key[0], key[1]] if prompted else [key[0]] if automatic else [key]
        self.assertEqual(game.accepted, expected)
        self.assertEqual(executor.ready_screen.kind, ScreenKind.COMMAND)
        self.assertFalse(game.term_fifo)
        self.assertFalse(game.screens, "every scheduled question was answered")
        policy.confirm_key_posted(key)
        return game

    def test_recorded_stop_is_adjacent_chest_and_direction_was_never_posted(self):
        for capture in self.captures:
            with self.subTest(capture=capture["capture"]):
                raw = capture["rows"][-1]
                self.assertEqual((raw["player"]["y"], raw["player"]["x"]), (9, 8))
                self.assertIn([10, 9, 1, 7], raw["grid_map"]["found_items"])
                self.assertEqual(capture["screen"]["input_context"]["kind"], "direction")
                self.assertTrue(capture["screen"]["input_context"]["at_feet"])
                self.assertEqual([row["character"] for row in capture["posted_tail"]][-3:], ["D", "D", "o"])
                match = classify_screen(capture["screen"], capture["stop_state"])
                self.assertEqual(match.kind, ScreenKind.DIRECTION)

    def test_recorded_search_disarm_open_pipeline_answers_every_direction(self):
        for capture in self.captures:
            with self.subTest(capture=capture["capture"]):
                policy = self.policy(capture)
                for raw, recorded in zip(capture["rows"], capture["decisions"]):
                    key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
                    self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]))
                    self.assertEqual(policy._chest_position, Position(10, 9))
                    self.post(policy, raw, key, capture["screen"])
                self.assertEqual(policy._chest_phase_counts["open"], 1)
                # DECLARED CONSTRUCTED: an unsuccessful lock pick returns to
                # command input, and the next attempt must answer afresh.
                raw = copy.deepcopy(capture["rows"][-1])
                raw["turn"] += 10
                key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
                self.assertEqual((key, policy.last_reason), ("o3", "chest:open"))
                self.post(policy, raw, key, capture["screen"])

    def test_recorded_open_stop_posts_the_adjacent_direction(self):
        for capture in self.captures:
            with self.subTest(capture=capture["capture"]):
                policy = self.policy(capture)
                raw = capture["rows"][-1]
                policy._observe(policy._with_grid_memory(parse_snapshot(raw, policy._monrace_knowledge)))
                # DECLARED CONSTRUCTED: restore the completed search/disarm
                # budgets shown in the decision tail; isolate the open stop.
                policy._chest_position = Position(10, 9)
                policy._chest_phase_counts = {"search": 6, "disarm": 2}
                key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
                self.assertEqual((key, policy.last_reason), ("o3", "chest:open"))
                self.post(policy, raw, key, capture["screen"])

    def test_easy_disarm_and_open_drop_only_unneeded_answers(self):
        capture = self.captures[0]
        for automatic in ((True, False, False), (False, True, True)):
            with self.subTest(automatic=automatic):
                policy = self.policy(capture)
                raw = copy.deepcopy(capture["rows"][-1])
                policy._observe(policy._with_grid_memory(parse_snapshot(raw, policy._monrace_knowledge)))
                # DECLARED CONSTRUCTED: resume immediately after the recorded
                # six searches. easy_disarm/easy_open may infer a direction
                # independently, so test both transitions without a stray 3.
                policy._chest_position = Position(10, 9)
                policy._chest_phase_counts = {"search": 6}
                for auto, expected in zip(automatic, ("D3", "D3", "o3")):
                    key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
                    self.assertEqual(key, expected)
                    self.post(policy, raw, key, capture["screen"], automatic=auto)
                    raw["turn"] += 10

    def test_source_english_at_feet_prompt_uses_same_follow_chain(self):
        capture = self.captures[0]
        policy = self.policy(capture)
        raw = capture["rows"][-1]
        policy._observe(policy._with_grid_memory(parse_snapshot(raw, policy._monrace_knowledge)))
        policy._chest_position = Position(10, 9)
        policy._chest_phase_counts = {"search": 6, "disarm": 1}
        # DECLARED CONSTRUCTED: exact English sibling of the captured prompt
        # from target/target-getter.cpp:get_rep_dir, without changing the map.
        screen = copy.deepcopy(capture["screen"])
        screen["lines"][0] = "Direction ('.' at feet, Escape to cancel)? "
        screen["input_context"]["prompt"] = screen["lines"][0]
        for expected in ("D3", "o3"):
            key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
            self.assertEqual(key, expected)
            self.post(policy, raw, key, screen)
