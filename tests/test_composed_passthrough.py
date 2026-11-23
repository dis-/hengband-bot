"""Composed keys sent whole are counted, and still sent as before (review 2026-11-23 K4, (a)-3).

observed_input.COMMAND_PROMPTS holds the questions an item command asks; a key such as a wand
letter + direction that compile_observed_input passes through whole is recorded in the
input-context log (``composed-passthrough``) without changing what goes to the game.
"""

import tests  # noqa: F401
import copy
import time
import unittest

from hengbot.cli import _ExecutorInputPort, _record_composed_passthrough
from hengbot.input_context import InputContextShadow
from hengbot.input_executor import ScreenKind
from hengbot.observed_input import COMMAND_PROMPTS, compile_observed_input, composed_passthrough
from tests.support import recorded as executor_harness
from tests.support.recorded import FaithfulHookGame, command_screen
from tests.test_classA_observed_input import board


class ComposedPassthroughRecordTest(unittest.TestCase):
    def test_item_commands_with_a_direction_pass_through_and_are_named(self):
        for key, suffix in (("ab6", "direction"), ("zc4", "direction"), ("vd2", "direction"),
                            ("fa*t5\x1b", "target-cursor"), ("fa*p66t5\x1b", "target-cursor"),
                            ("T6", "direction"), ("+6y", "direction")):
            with self.subTest(key=key):
                prefix, steps = compile_observed_input(key, ScreenKind.COMMAND, {}, "melee", [])
                self.assertEqual((prefix, steps), (key, []))
                record = composed_passthrough(key, prefix)
                self.assertEqual((record["command"], record["key"], record["suffix"]),
                                 (key[0], key, suffix))
                self.assertEqual(len(record["expected"]), len(COMMAND_PROMPTS[key[0]]))

    def test_gated_and_single_keys_are_not_recorded(self):
        # 'o' + direction is released only at the observed question (6bef1941c0); a quaff's
        # item letter at its observed chooser; a bare move has no table row.
        for key in ("o6", "qc"):
            with self.subTest(key=key):
                prefix, _steps = compile_observed_input(key, ScreenKind.COMMAND, {}, "melee", [])
                self.assertEqual(prefix, key[0])
                self.assertIsNone(composed_passthrough(key, prefix))
        self.assertIsNone(composed_passthrough("6", "6"))
        self.assertIsNone(composed_passthrough("R&\r", "R&\r"))

    def test_shadow_counts_and_logs_each_passthrough(self):
        shadow = InputContextShadow(None)

        class _Executor:
            input_context_shadow = shadow

        _record_composed_passthrough(_Executor(), "ranged:fire-target", "fa*t5\x1b", "fa*t5\x1b")
        _record_composed_passthrough(_Executor(), "melee", "ab6", "ab6")
        _record_composed_passthrough(_Executor(), "melee", "ab6", "ab6")
        _record_composed_passthrough(_Executor(), "door", "o6", "o")
        self.assertEqual(shadow.counts()["composed_passthrough"],
                         {"f:target-cursor": 1, "a:direction": 2})

    def test_recording_failure_never_stops_the_send(self):
        class _Broken:
            def composed_passthrough(self, owner, record):
                raise RuntimeError("log down")

        class _Executor:
            input_context_shadow = _Broken()

        _record_composed_passthrough(_Executor(), "melee", "ab6", "ab6")
        _record_composed_passthrough(object(), "melee", "ab6", "ab6")


class ComposedPassthroughPortTest(executor_harness.ProductionHarness):
    def test_port_sends_the_same_key_and_counts_it(self):
        game = FaithfulHookGame()
        game.state = copy.deepcopy(board())
        game.screen = command_screen(game.state["turn"])
        game.screens = [command_screen(2)]
        game.states = [copy.deepcopy(game.state)]
        _, _client, executor = self.make(game)
        shadow = InputContextShadow(None)
        executor.input_context_shadow = shadow
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 1).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=False, request_budget=0.2)
        port.submit_operation("ab6", decision={"sequence": 1, "reason": "melee"})
        self.assertEqual(game.accepted, ["ab6"])
        self.assertEqual(shadow.composed_passthroughs, {"a:direction": 1})


if __name__ == "__main__":
    unittest.main()
