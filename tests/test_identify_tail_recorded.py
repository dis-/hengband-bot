"""10/27 recorded decisions and absent target barriers through the real sender.

The captures retain the final screen and JSONL boards, not the intermediate
staff chooser. That chooser is source-derived from the recorded inventory.
Its history uses the preceding JSONL's final repeated message; the final TCP
history is recorded. Constructed chooser/address controls stop at the first
new target answer and claim no recorded identification effect.
"""
import tests  # noqa: F401
import copy
import hashlib
import json
from pathlib import Path
import sys
import time
import unittest

from hengbot.cli import _ExecutorInputPort, _send_decision_key_with_prompt_chain
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import ConservativePolicy
from hengbot.policy_identification import SOURCE_PROMPT, IDENTIFY_ITEM_PROMPT
from tests import test_input_executor as harness

# Bare unittest and package imports must share this harness's class objects.
sys.modules.setdefault("test_identify_tail_recorded", sys.modules[__name__])
sys.modules.setdefault("tests.test_identify_tail_recorded", sys.modules[__name__])

FIXTURES = Path(__file__).with_name("fixtures") / "identify-tail-1027"


def load(label):
    return json.loads((FIXTURES / (label + ".json")).read_text(encoding="utf-8"))


def chooser(board, source=True, japanese=True):
    prefix = "(持ち物:a-z, ESC) " if japanese else "(Inven:a-z, ESC) "
    prompts = SOURCE_PROMPT["u"] if source else IDENTIFY_ITEM_PROMPT
    screen = harness.prompt_screen(prefix + prompts[0 if japanese else 1].rstrip())
    items = [item for item in board["inventory"] if not source or item["tval"] == 55]
    for row, item in enumerate(items, 1):
        screen["lines"][row] = item["slot"] + ") " + item["name"]
    return screen


class StopAfterTarget(harness.FaithfulHookGame):
    def hook(self, request):
        if request["op"] == "screen" and len(self.accepted) == 3:
            return {"id": request["id"], "ok": False,
                    "error": "no post-divergence capture"}, None
        return super().hook(request)


class IdentifyTailRecordedPin(harness.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(Path("C:/hengband/lib/edit/MonraceDefinitions.jsonc"))

    def drive(self, label="151412", *, target=None, japanese=True,
              owner=None, unchanged_history=False, repeat_delta=False):
        data = load(label)
        before, after = data["before"], copy.deepcopy(data["after"])
        # Derived inner prompt state, carrying the recorded prior failure count.
        source = copy.deepcopy(before)
        final_history = data["after_history"]
        after["messages"] = final_history
        final_screen = copy.deepcopy(data["screen"])
        if unchanged_history:
            after["messages"] = source["messages"]
            final_screen["lines"][0] = "An unrelated message."
        if repeat_delta:
            after["messages"] = ["You failed to use the staff properly. <x2>"]
            final_screen["lines"][0] = "An unrelated message."
        game = StopAfterTarget() if target is not None else harness.FaithfulHookGame()
        game.state = copy.deepcopy(before)
        game.screen = harness.command_screen(before["turn"])
        game.screens = [chooser(source, japanese=japanese),
                        chooser(target, False, japanese) if target is not None else final_screen]
        game.states = [source, target if target is not None else after]
        _, client, executor = self.make(game)
        # Model the unread JSONL delta separately from TCP message history.
        records = []
        def drain():
            if len(game.accepted) == 2 and target is None:
                value = copy.deepcopy(data["after"])
                if repeat_delta:
                    value["messages"] = after["messages"]
                if unchanged_history:
                    value["messages"] = ["An unrelated message."]
                if not records:
                    records.append(value)
                    return [value]
            return []
        executor.drain = drain
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 2).outcome, "ready")
        policy = ConservativePolicy()
        policy.consume_skill_knowledge(load("skill-knowledge"))
        snapshot = parse_snapshot(before, self.monrace)
        key = policy.choose_key(snapshot)
        self.assertEqual((key, policy.last_reason), (data["decision"]["key"], data["decision"]["reason"]))
        port = _ExecutorInputPort(executor, tunnel_macros_ready=False, request_budget=0.5)
        decision = dict(sequence=data["decision"]["decision_sequence"], reason=owner or policy.last_reason,
                        key=key)
        sent, _, _, chain = _send_decision_key_with_prompt_chain(
            port, label, key, None, set(), policy=policy, shadow_client=client,
            file=None, deadline=time.monotonic() + 2, poll_interval=0,
            prompt_japanese=not japanese, decision=decision, snapshot=snapshot,
            posting_contract=None, in_store=False)
        return game, port.last_result, sent, chain

    def test_recorded_capture_hashes_and_posted_prefixes(self):
        for label, info in load("provenance").items():
            with self.subTest(label=label):
                self.assertEqual(hashlib.sha256((FIXTURES / (label + ".json")).read_bytes()).hexdigest(),
                                 info["sha256"])
                self.assertEqual([row["character"] for row in load(label)["posted"]], ["u", "g"])

    def test_recorded_concatenated_failure_completes_with_named_refusal(self):
        game, result, sent, chain = self.drive("151405")
        self.assertEqual(game.accepted, ["u", "g"])
        self.assertEqual(result.outcome, "completed", result.reason)
        self.assertEqual(result.operation.business_outcome, "refused:source-command")
        self.assertTrue(sent)
        self.assertEqual(chain["outcome"], "released")
        self.assertFalse(result.board["inventory"][8]["known"])

    def test_recorded_repeated_failure_outside_delta_completes(self):
        game, result, sent, chain = self.drive()
        self.assertEqual(game.accepted, ["u", "g"])
        self.assertEqual(result.outcome, "completed", result.reason)
        self.assertEqual(result.operation.business_outcome, "refused:source-command")
        self.assertEqual(result.operation.dropped_continuations, ["i"])
        self.assertTrue(sent)
        self.assertEqual(chain["outcome"], "released")

    def test_unchanged_old_failure_does_not_complete(self):
        game, result, sent, _ = self.drive(unchanged_history=True)
        self.assertEqual(game.accepted, ["u", "g"])
        self.assertEqual(result.outcome, "stuck-prompt")
        self.assertFalse(sent)

    def test_repetition_suffix_in_fresh_delta_is_recognized(self):
        game, result, _, _ = self.drive(repeat_delta=True)
        self.assertEqual(game.accepted, ["u", "g"])
        self.assertEqual(result.outcome, "completed", result.reason)

    def test_dungeon_and_pressure_rebind_visible_target_for_both_languages(self):
        for owner in ("identify:dungeon-equipment", "identify:pack-pressure"):
            for japanese in (False, True):
                with self.subTest(owner=owner, japanese=japanese):
                    target = load("151412")["before"]
                    target["inventory"][8]["slot"] = "k"
                    game, result, _, _ = self.drive(target=target, owner=owner, japanese=japanese)
                    self.assertEqual(game.accepted, ["u", "g", "k"])
                    self.assertEqual(result.operation.continuations, [])


if __name__ == "__main__":
    unittest.main()
