"""Live17: production decisions omit observation; bind the observed ready board.

The source screen is the unchanged 00:47 capture, whose row zero also appears
in the 02:21 terminal diagnostic. The ready state is the last snapshot in the
02:21 frozen capture. The target is the live13 equipment chooser. No result
was captured after our new answer: the recorded pin stops at that divergence.
"""
import tests  # noqa: F401
import copy
import json
import time
from pathlib import Path

from hengbot.cli import _ExecutorInputPort, _send_decision_key_with_prompt_chain
from hengbot.model import parse_snapshot
from hengbot.policy import ConservativePolicy
import tests.test_input_executor as input_executor_tests
from tests.test_live15_identify_source import StopAfterTargetGame
from tests.test_input_executor import FaithfulHookGame, source_derived_identify_viewer

FIXTURES = Path(__file__).with_name("fixtures") / "live-screens"


class Live17IdentifyObservationPin(input_executor_tests.ProductionHarness):
    def test_live_decision_without_injected_observation(self):
        for japanese in (False, True):
            with self.subTest(prompt_japanese=japanese):
                state = json.loads((FIXTURES / "live17-before-identify-state.json").read_text(encoding="utf-8"))
                source = json.loads((FIXTURES / "live15-read-scroll-prompt.json").read_text(encoding="utf-8"))
                target = json.loads((FIXTURES / "live13-star-identify-equipment-prompt.json").read_text(encoding="utf-8"))
                policy = ConservativePolicy()
                snapshot = parse_snapshot(state, {})
                key = policy._town_equipped_identification_key(snapshot)
                self.assertEqual((key, policy.last_reason), ("rfa", "identify:full-equipped"))
                game = StopAfterTargetGame()
                game.state = copy.deepcopy(state)
                game.screens = [source, target]
                game.states = [copy.deepcopy(state), copy.deepcopy(state)]
                _, client, executor = self.make(game)
                self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 1).outcome, "ready")
                board = executor.ready_board
                port = _ExecutorInputPort(executor, tunnel_macros_ready=False, request_budget=0.2)
                # Exactly the fields constructed by both live main-loop paths.
                decision = dict(sequence=1, turn=snapshot.turn,
                                reason=policy.last_reason, key=key,
                                prompt_owner_handoff=policy.prompt_owner_handoff)
                _, _, _, result = _send_decision_key_with_prompt_chain(
                    port, "recorded", key, None, set(), policy=policy,
                    shadow_client=client, file=None, deadline=time.monotonic() + 1,
                    poll_interval=0, prompt_japanese=japanese, decision=decision,
                    snapshot=snapshot, posting_contract=None, in_store=False,
                )
                self.assertEqual(game.accepted, ["r", "f", "a"])
                self.assertIs(port.last_result.operation.observation, board)
                self.assertEqual(result["released_through"], 2)
                self.assertEqual(result["posted"], "rfa")
                self.assertEqual(port.last_result.outcome, "stuck-prompt")
                self.assertIn("phase=screen", port.last_result.reason)
                self.assertEqual(port.last_result.operation.continuations, [])

    def test_source_derived_inventory_switch_and_observed_result(self):
        # Only the source and equipment chooser are recorded. The intervening
        # inventory chooser and result viewer are source-derived protocol
        # variants, not claimed to be additional live17 captures.
        for inventory_first in (False, True):
            with self.subTest(inventory_first=inventory_first):
                state = json.loads((FIXTURES / "live17-before-identify-state.json").read_text(encoding="utf-8"))
                source = json.loads((FIXTURES / "live15-read-scroll-prompt.json").read_text(encoding="utf-8"))
                target = json.loads((FIXTURES / "live13-star-identify-equipment-prompt.json").read_text(encoding="utf-8"))
                game = FaithfulHookGame()
                game.state = copy.deepcopy(state)
                game.screens = [source, target]
                if inventory_first:
                    inventory = copy.deepcopy(target)
                    inventory["lines"][0] = "(Inven:a-z,'/' for Equip, ESC) *Identify* which item?"
                    game.screens.insert(1, inventory)
                game.screens.extend([source_derived_identify_viewer(),
                                     source_derived_identify_viewer(final=True),
                                     input_executor_tests.command_screen(state["turn"] + 1)])
                game.states = [copy.deepcopy(state) for _ in game.screens]
                _, client, executor = self.make(game)
                self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 1).outcome, "ready")
                policy = ConservativePolicy()
                snapshot = parse_snapshot(state, {})
                key = policy._town_equipped_identification_key(snapshot, macro=True)
                port = _ExecutorInputPort(executor, tunnel_macros_ready=False, request_budget=0.2)
                _, _, _, result = _send_decision_key_with_prompt_chain(
                    port, "source-derived", key, None, set(), policy=policy,
                    shadow_client=client, file=None, deadline=time.monotonic() + 1,
                    poll_interval=0, prompt_japanese=False,
                    decision=dict(sequence=1, turn=snapshot.turn, reason=policy.last_reason,
                                  key=key, prompt_owner_handoff=policy.prompt_owner_handoff),
                    snapshot=snapshot, posting_contract=None, in_store=False,
                )
                self.assertEqual(game.accepted, ["r", "f"] + (["/"] if inventory_first else []) + ["a", " ", "\x1b"])
                self.assertEqual(port.last_result.outcome, "completed")
                self.assertEqual(result["outcome"], "released")
