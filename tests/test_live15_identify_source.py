"""Recorded live15 source and live13 target through the production input port.

No result was captured after the new answer; stop at that first divergence.
"""
import tests  # noqa: F401
import copy
import json
import time
from pathlib import Path

from hengbot.cli import _ExecutorInputPort, _send_prompt_gated_decision_key
from hengbot.model import parse_snapshot
from hengbot.policy import ConservativePolicy
import tests.test_input_executor as input_executor_tests
from tests.test_input_executor import FaithfulHookGame

FIXTURES = Path(__file__).with_name("fixtures") / "live-screens"


class StopAfterTargetGame(FaithfulHookGame):
    def hook(self, request):
        if request["op"] == "screen" and self.accepted[-1:] == ["a"]:
            return {"id": request["id"], "ok": False,
                    "error": "no post-divergence capture"}, None
        return super().hook(request)


class Live15IdentifySourcePin(input_executor_tests.ProductionHarness):
    def test_recorded_source_and_equipment_through_cli(self):
        for japanese in (False, True):
            with self.subTest(prompt_japanese=japanese):
                state = json.loads((FIXTURES / "live13-before-identify-state.json").read_text(encoding="utf-8"))
                source = json.loads((FIXTURES / "live15-read-scroll-prompt.json").read_text(encoding="utf-8"))
                target = json.loads((FIXTURES / "live13-star-identify-equipment-prompt.json").read_text(encoding="utf-8"))
                policy = ConservativePolicy()
                key = policy._town_equipped_identification_key(parse_snapshot(state, {}))
                self.assertEqual((key, policy.last_reason), ("rfa", "identify:full-equipped"))
                game = StopAfterTargetGame()
                game.state = copy.deepcopy(state)
                game.screens = [source, target]
                game.states = [copy.deepcopy(state), copy.deepcopy(state)]
                _, client, executor = self.make(game)
                self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 1).outcome, "ready")
                port = _ExecutorInputPort(executor, tunnel_macros_ready=False, request_budget=0.2)
                _send_prompt_gated_decision_key(
                    port, "recorded", key, None, set(), policy.peek_staged_prompt_chain(),
                    shadow_client=client, file=None, deadline=time.monotonic() + 1,
                    poll_interval=0, prompt_japanese=japanese,
                    decision={"sequence": 1, "reason": policy.last_reason, "observation": state},
                    snapshot=None, posting_contract=None,
                )
                self.assertEqual(game.accepted, ["r", "f", "a"])
                self.assertEqual(port.last_result.outcome, "stuck-prompt")
                self.assertEqual(port.last_result.operation.continuations, [])
                self.assertIn("phase=screen", port.last_result.reason)
