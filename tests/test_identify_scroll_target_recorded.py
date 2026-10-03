"""Captured duplicate-target incident through the production observed input port.

Only the failed chooser's row zero is recorded. Item rows and source chooser
are derived from captured inventory and production literals. Command waits
are constructed protocol controls; runs stop at the first new target answer,
without inventing its effect. Address/identity variants are constructed controls.
"""
import tests  # noqa: F401
import copy
import hashlib
import json
import time
from pathlib import Path

from hengbot.cli import _ExecutorInputPort
from hengbot.policy_identification import SOURCE_PROMPT
from tests import test_input_executor as harness
from tests.test_live30_identify_normal import StopAfterNewTarget


FIXTURES = Path(__file__).with_name("fixtures") / "identify-scroll-target"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def chooser(board, prompt, slots):
    screen = harness.prompt_screen(prompt)
    for row, item in enumerate((item for item in board["inventory"]
                                if item["slot"] in slots), 1):
        screen["lines"][row] = item["slot"] + ") " + item["name"]
    return screen


class IdentifyScrollTargetPin(harness.ProductionHarness):
    def drive(self, *, name="before-rhm.json", target_board=None, target_prompt=None):
        before = load(name)
        target_board = copy.deepcopy(target_board or before)
        source = chooser(before, "(Inven:h-h, ESC) " + SOURCE_PROMPT["r"][1].rstrip(), "h")
        # Row zero is verbatim stderr evidence for rhm. Reusing that same
        # prompt for rho is a declared control, not a captured success screen.
        target = chooser(target_board, target_prompt or load("provenance.json")[
            "captured_target_prompt"], "mnopqrstuvwxyz")
        game = StopAfterNewTarget()
        game.state = copy.deepcopy(before)
        game.screen = harness.command_screen(before["turn"])
        game.screens = [source, target]
        game.states = [copy.deepcopy(before), target_board]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 1).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=False, request_budget=0.2)
        key = "rho" if name == "before-rho.json" else "rhm"
        port.submit_operation(key, decision={"sequence": 1177, "reason": "identify:normal"})
        return game, port.last_result

    def test_capture_hashes_and_duplicate_identity(self):
        for name, metadata in load("provenance.json")["boards"].items():
            self.assertEqual(hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest(),
                             metadata["sha256"])
        items = {item["slot"]: item for item in load("before-rhm.json")["inventory"]}
        self.assertEqual(tuple(items["m"][field] for field in ("tval", "sval", "name")),
                         tuple(items["n"][field] for field in ("tval", "sval", "name")))
        self.assertFalse(items["m"]["known"])
        self.assertFalse(items["n"]["known"])

    def test_recorded_duplicate_target_answers_original_slot(self):
        game, result = self.drive()
        self.assertEqual(game.accepted, ["r", "h", "m"])
        self.assertEqual(result.operation.continuations, [])
        self.assertEqual(result.outcome, "stuck-prompt")  # No post-divergence capture.
        self.assertIn("read-only request failed", result.reason)

    def test_recorded_rho_inventory_has_unique_target(self):
        before = load("before-rho.json")
        old = next(item for item in before["inventory"] if item["slot"] == "o")
        self.assertEqual(sum(all(item[field] == old[field] for field in ("tval", "sval", "name"))
                             for item in before["inventory"]), 1)
        game, _ = self.drive(name="before-rho.json")
        self.assertEqual(game.accepted, ["r", "h", "o"])

    def test_ambiguous_relocation_withholds_target(self):
        target = load("before-rhm.json")
        for item in target["inventory"]:
            if item["slot"] == "m":
                item["slot"] = "s"
        game, result = self.drive(target_board=target)
        self.assertEqual(game.accepted, ["r", "h"])
        self.assertIn("unowned item-target", result.reason)

    def test_unique_relocation_rebinds_target(self):
        target = load("before-rhm.json")
        target["inventory"] = [item for item in target["inventory"] if item["slot"] != "n"]
        next(item for item in target["inventory"] if item["slot"] == "m")["slot"] = "n"
        game, _ = self.drive(target_board=target)
        self.assertEqual(game.accepted, ["r", "h", "n"])

    def test_changed_identity_with_ambiguous_matches_withholds_target(self):
        target = load("before-rhm.json")
        extra = copy.deepcopy(next(item for item in target["inventory"] if item["slot"] == "m"))
        extra["slot"] = "s"
        target["inventory"].append(extra)
        next(item for item in target["inventory"] if item["slot"] == "m")["name"] = "Changed item"
        game, result = self.drive(target_board=target)
        self.assertEqual(game.accepted, ["r", "h"])
        self.assertIn("unowned item-target", result.reason)

    def test_wrong_chooser_never_answers_target(self):
        for prompt in ("(Inven:m-r, ESC) Enchant which item?",
                       "(Inven:m-r, ESC) *Identify* which item?",
                       "(Equip:m-r, ESC) Identify which item?"):
            with self.subTest(prompt=prompt):
                game, result = self.drive(target_prompt=prompt)
                self.assertEqual(game.accepted, ["r", "h"])
                self.assertEqual(result.outcome, "stuck-prompt")

    def test_missing_visible_target_withholds_answer(self):
        target = load("before-rhm.json")
        # Unique relocation to a) in state, but the constructed screen omits
        # that label: state alone must not authorize an invisible selection.
        for item in target["inventory"]:
            if item["slot"] == "m":
                item["slot"] = "a"
        target["inventory"] = [item for item in target["inventory"] if item["slot"] != "n"]
        game, result = self.drive(target_board=target)
        self.assertEqual(game.accepted, ["r", "h"])
        self.assertIn("unowned item-target", result.reason)
