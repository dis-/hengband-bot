"""Slice S0 of the control-server input context: record it, decide nothing from it.

plans/DESIGN-control-context-1022.md sections 6.1, 6.3, 7 and 8.  The reader
has four states; the executor's classification, keys and outcomes are the same
whether or not the game publishes ``input_context``; the stderr stop line names
the context before ``reason=``; agreements, disagreements and residual tails
are counted and logged beside the decision log.
"""

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs

import copy
import gzip
import json
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from hengbot.cli import _ExecutorInputPort
from hengbot.input_context import (
    INPUT_CONTEXT_SHADOW_NAME, InputContextShadow, compatible_kinds, current_input_state,
    read_input_context, stop_line_fields,
)
from hengbot.input_executor import (
    Continuation, Operation, OperationExecutor, ScreenKind, classify_screen,
)
from hengbot.runtime_paths import runtime_path
from tests import test_input_executor as executor_harness
from tests.test_input_executor import FaithfulHookGame, command_screen, prompt_screen


FIXTURES = Path(__file__).with_name("fixtures")
# DECLARED CONSTRUCTED from tools/bot/README.md @ 04e95fb52c ("input_context").
CONFIRM = {"kind": "confirm", "prompt": "本当にこの階を去りますか？[y/n]"}
COMMAND = {"kind": "command", "prompt": "", "shopping": False}
DEPARTURE_QUESTION = "本当にこの階を去りますか？[y/n]"


# Every fixture that keeps a recorded screen reply (a "lines" list), found by
# scanning tests/fixtures at 17b8907c: 30 screens.
RECORDED_SCREEN_FIXTURES = (
    "24-town3-reward-pack-full-stop.json", "live-screen-idle-town0-20260913.json",
    "live35-store-page.json", "screen-19-29-knowledge.json",
    "screen-20260920-levelup-stat-prompt.json", "sol-events.jsonl.gz",
    "equipment-home-stage1.screen.json.gz", "fundraise-kit-poor-20261018.json.gz",
    "fundraise-kit-retired-20261019.json.gz", "fundraise-kit-route-20261018.json.gz",
    "home-leave-suppressed-20261019.json.gz", "idstaff-fundraise-20261020.json.gz",
    "idstaff-poor-depart-20261019.json.gz", "no-safe-dest-gold-20261019.json.gz",
    "recall-churn-stockout-20261018.json.gz", "supply-shortfall-owner-20261018.json.gz",
    "travel-interrupted-screen-20260915.json.gz",
)


def recorded_screens():
    """Every recorded screen reply kept in tests/fixtures (old game, no context)."""
    found = []

    def walk(value, name):
        if isinstance(value, dict):
            lines = value.get("lines")
            if isinstance(lines, list) and lines and all(isinstance(line, str) for line in lines):
                found.append((name, value))
                return
            for item in value.values():
                walk(item, name)
        elif isinstance(value, list):
            for item in value:
                walk(item, name)

    for path in (FIXTURES / name for name in RECORDED_SCREEN_FIXTURES):
        if path.name.endswith(".json"):
            walk(json.loads(path.read_text(encoding="utf-8")), path.name)
        elif path.name.endswith((".json.gz", ".jsonl.gz")):
            with gzip.open(path, "rt", encoding="utf-8") as stream:
                text = stream.read()
            rows = [text] if path.name.endswith(".json.gz") else text.splitlines()
            for row in rows:
                try:
                    walk(json.loads(row), path.name)
                except ValueError:
                    continue
    return found


def with_context(value, context):
    published = copy.deepcopy(value)
    published["input_context"] = copy.deepcopy(context)
    return published


class NewGame(FaithfulHookGame):
    """The same fake game, publishing ``input_context`` on screen and state."""

    def __init__(self, context_for):
        super().__init__()
        self.context_for = context_for

    def hook(self, request):
        response, fault = super().hook(request)
        if response is not None and request["op"] in ("screen", "state") and response.get("ok"):
            response = copy.deepcopy(response)
            response["result"]["input_context"] = self.context_for(self.screen)
        return response, fault


def context_of_screen(screen):
    return CONFIRM if screen["lines"][0].endswith("[y/n]") else COMMAND


class ReaderStates(unittest.TestCase):
    def test_four_states_are_never_confused(self):
        self.assertEqual(read_input_context(None).source, "unavailable")
        self.assertEqual(read_input_context(["lines"]).source, "unavailable")
        self.assertEqual(read_input_context({"lines": []}).source, "absent")
        self.assertEqual(read_input_context({"input_context": None}).source, "null")
        self.assertEqual(read_input_context({"input_context": "confirm"}).source, "unavailable")
        self.assertEqual(read_input_context({"input_context": {"prompt": "x"}}).source, "unavailable")
        reading = read_input_context({"input_context": {
            "kind": "quantity", "prompt": "いくつですか (1-5): ", "max": 5, "initial": 1}})
        self.assertEqual((reading.source, reading.kind, reading.prompt, dict(reading.details)),
                         ("server", "quantity", "いくつですか (1-5): ", {"max": 5, "initial": 1}))

    def test_stop_line_fields_name_the_kind_or_the_source(self):
        self.assertEqual(stop_line_fields(read_input_context({"lines": []})),
                         'ctx=absent ctx_prompt=""')
        self.assertEqual(stop_line_fields(read_input_context(None)),
                         'ctx=unavailable ctx_prompt=""')
        self.assertEqual(stop_line_fields(read_input_context({"input_context": None})),
                         'ctx=null ctx_prompt=""')
        self.assertEqual(stop_line_fields(read_input_context({"input_context": CONFIRM})),
                         'ctx=confirm ctx_prompt="本当にこの階を去りますか？[y/n]"')


class RecordedScreensKeepTheirClassification(unittest.TestCase):
    """Old game pin: every recorded screen classifies exactly as before, reads
    ``absent``, and a published context changes no classification."""

    def test_every_recorded_screen(self):
        screens = recorded_screens()
        self.assertEqual(len(screens), 30)
        self.assertEqual({name for name, _screen in screens}, set(RECORDED_SCREEN_FIXTURES))
        for name, screen in screens:
            with self.subTest(fixture=name, row0=screen["lines"][0][:40]):
                before = classify_screen(screen)
                observed = current_input_state(screen)
                self.assertEqual(observed.match, before)
                self.assertEqual(observed.reading.source, "absent")
                self.assertIn(observed.verdict, {"no-context", "death"})
                for context in (CONFIRM, COMMAND, None):
                    published = current_input_state(with_context(screen, context))
                    self.assertEqual(published.match, before)

    def test_verdicts_compare_the_context_with_the_classifier(self):
        confirm = prompt_screen(DEPARTURE_QUESTION)
        self.assertEqual(current_input_state(with_context(confirm, CONFIRM)).verdict, "agree")
        self.assertEqual(current_input_state(with_context(confirm, COMMAND)).verdict, "disagree")
        self.assertEqual(current_input_state(with_context(confirm, None)).verdict, "no-context")
        store = with_context(command_screen(), {"kind": "command", "prompt": "", "shopping": True})
        self.assertEqual(current_input_state(store).verdict, "disagree")


class NewContextKindsTest(unittest.TestCase):
    """Game develop 92e9029a adds the spell, building, file and birth contexts.

    DECLARED CONSTRUCTED: the published contexts (tools/bot/README.md
    "input_context" at 92e9029a) on recorded screens of the matching kind.
    """

    def test_recorded_screens_agree_with_the_new_kinds(self):
        screens = {}
        for name, screen in recorded_screens():
            screens.setdefault(classify_screen(screen).kind, (name, screen))
        cases = (
            (ScreenKind.BUILDING, {"kind": "building", "prompt": ""}),
            (ScreenKind.UNKNOWN, {"kind": "spell", "prompt": "どの呪文を唱えますか?",
                                  "first_label": "a", "last_label": "h", "list": False,
                                  "browse": False, "menu": False}),
            (ScreenKind.UNKNOWN, {"kind": "file",
                                  "prompt": "[キー:(RET/スペース)↓ (-)↑ (?)ヘルプ (ESC)終了]"}),
            (ScreenKind.UNKNOWN, {"kind": "birth", "prompt": "性別を選んで下さい", "step": "sex"}),
        )
        for kind, context in cases:
            name, screen = screens[kind]
            with self.subTest(context=context["kind"], fixture=name):
                self.assertEqual(current_input_state(with_context(screen, context)).verdict, "agree")
        file_context = read_input_context({"input_context": {"kind": "file", "prompt": ""}})
        self.assertIn(ScreenKind.FILE_VIEWER, compatible_kinds(file_context))


class ExecutorRecordsWithoutDeciding(executor_harness.ProductionHarness):
    def drive_unowned_confirm(self, game, shadow=None):
        client_game, client, _executor = self.make(game)
        executor = OperationExecutor(client, drain=lambda: list(client_game.jsonl),
                                     input_context_shadow=shadow)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        game.screens = [prompt_screen(DEPARTURE_QUESTION)]
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        stderr = StringIO()
        with redirect_stderr(stderr):
            sent = port("<", decision={"sequence": 7, "reason": "breeder-breakthrough:ascend"})
        return port, sent, stderr.getvalue()

    def test_old_game_stop_line_reads_absent_and_nothing_else_changes(self):
        game = FaithfulHookGame()
        port, sent, stderr = self.drive_unowned_confirm(game)
        expected_reason = (
            "<stuck-prompt> owner=breeder-breakthrough:ascend phase=continuation "
            "transport=accepted request_id=3 reason=unowned confirm: " + DEPARTURE_QUESTION)
        self.assertEqual(port.last_result.reason, expected_reason)
        self.assertEqual(
            stderr,
            "<stuck-prompt> owner=breeder-breakthrough:ascend phase=continuation "
            'transport=accepted request_id=3 ctx=absent ctx_prompt="" '
            "reason=unowned confirm: " + DEPARTURE_QUESTION + "\n")
        self.assertEqual(game.accepted, ["<"])
        shadow = port.executor.input_context_shadow
        self.assertEqual(shadow.agreements, {})
        self.assertEqual(shadow.disagreements, {})
        self.assertEqual(set(shadow.without_context), {"absent"})

    def test_new_game_posts_the_same_keys_and_names_the_context(self):
        old = FaithfulHookGame()
        old_port, old_sent, _old_stderr = self.drive_unowned_confirm(old)
        new = NewGame(context_of_screen)
        port, sent, stderr = self.drive_unowned_confirm(new)
        self.assertEqual((sent, new.accepted, port.last_result.outcome, port.last_result.reason),
                         (old_sent, old.accepted, old_port.last_result.outcome,
                          old_port.last_result.reason))
        self.assertIn('request_id=3 ctx=confirm ctx_prompt="本当にこの階を去りますか？[y/n]" '
                      "reason=unowned confirm: ", stderr)
        shadow = port.executor.input_context_shadow
        self.assertEqual(shadow.agreements, {"command": 1, "confirm": 1})
        self.assertEqual(shadow.disagreements, {})

    def test_admission_refusal_prints_the_context_too(self):
        game = NewGame(context_of_screen)
        with patch("hengbot.observed_input.compile_observed_input",
                   side_effect=ValueError("uncompilable")):
            port, sent, stderr = self.drive_unowned_confirm(game)
        self.assertEqual(game.accepted, [])
        self.assertEqual(
            stderr,
            "<stuck-prompt> owner=breeder-breakthrough:ascend phase=admission "
            'transport=tcp request_id=None ctx=command ctx_prompt="" reason=uncompilable\n')

    def test_lost_screen_reads_unavailable_not_absent(self):
        game, _client, executor = self.make()
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        original = game.hook

        def lose_post_ack_screens(request):
            response, fault = original(request)
            if request["op"] == "screen" and game.accepted:
                return None, fault
            return response, fault

        game.hook = lose_post_ack_screens
        result = executor.submit(
            Operation(79, "identify:full-equipped", "rg/j", executor.ready_board,
                      response_grace=0.01),
            deadline=time.monotonic() + 0.5,
        )
        self.assertEqual(result.reason, "<stuck-prompt> owner=identify:full-equipped "
                         "phase=screen transport=accepted request_id=3 "
                         "reason=read-only request failed")
        self.assertEqual(result.stop_line, "<stuck-prompt> owner=identify:full-equipped "
                         "phase=screen transport=accepted request_id=3 "
                         'ctx=unavailable ctx_prompt="" reason=read-only request failed')


class ShadowLog(executor_harness.ProductionHarness):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / INPUT_CONTEXT_SHADOW_NAME

    def rows(self):
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines()]

    def test_default_log_is_the_runtime_file(self):
        game = FaithfulHookGame()
        game, client, executor = self.make(game)
        self.assertEqual(executor.input_context_shadow.path, runtime_path(INPUT_CONTEXT_SHADOW_NAME))

    def test_disagreement_and_stop_counts_are_logged(self):
        # The game says the departure question is open while the row reads like
        # a map: a disagreement line, then the counts at the stop.
        game = NewGame(lambda screen: CONFIRM)
        game, client, _executor = self.make(game)
        executor = OperationExecutor(client, drain=lambda: list(game.jsonl),
                                     input_context_shadow=InputContextShadow(self.path))
        boundary = executor.observe_boundary(deadline=9999999999)
        self.assertEqual(boundary.outcome, "ready")   # S0: the classifier still decides
        unknown = prompt_screen("Unrecognised prompt")
        unknown["cursor"] = {"visible": True, "y": 0, "x": 19}
        game.screens = [unknown]
        result = executor.submit(Operation(3, "melee", "6", executor.ready_board),
                                 deadline=9999999999)
        self.assertEqual(result.outcome, "stuck-prompt")
        rows = self.rows()
        disagreements = [row for row in rows if row["event"] == "disagree"]
        self.assertEqual([(row["owner"], row["context"]["kind"], row["heuristic"]["kind"])
                          for row in disagreements],
                         [(None, "confirm", "command"), ("melee", "confirm", "unknown")])
        self.assertEqual(disagreements[1]["row0"], "Unrecognised prompt")
        self.assertEqual(rows[-1]["event"], "counts")
        self.assertEqual(rows[-1]["counts"]["disagree"], {"confirm": 2})
        self.assertIn("ctx=confirm", rows[-1]["stop"])

    def test_residual_tail_at_a_command_barrier_is_counted_per_owner(self):
        game = NewGame(context_of_screen)
        game, client, _executor = self.make(game)
        shadow = InputContextShadow(self.path)
        executor = OperationExecutor(client, drain=lambda: list(game.jsonl),
                                     input_context_shadow=shadow)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        operation = Operation(
            11, "identify:normal", "u", executor.ready_board,
            continuations=[Continuation(frozenset({ScreenKind.ITEM_SOURCE}), "m")],
            response_grace=0.01)
        result = executor.submit(operation, deadline=9999999999)
        self.assertEqual(result.outcome, "stuck-prompt")
        self.assertIn("expected prompt absent", result.reason)
        self.assertEqual(shadow.residual_continuations, {"identify:normal": {"command": 1}})
        residual = [row for row in self.rows() if row["event"] == "residual-continuations"]
        self.assertEqual([(row["owner"], row["context"]["kind"]) for row in residual],
                         [("identify:normal", "command")])

    def test_death_writes_the_counts(self):
        game, client, _executor = self.make()
        executor = OperationExecutor(client, drain=lambda: list(game.jsonl),
                                     input_context_shadow=InputContextShadow(self.path))
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        game.screens = [prompt_screen("あなたは死にました。")]
        result = executor.submit(Operation(5, "melee", "6", executor.ready_board),
                                 deadline=9999999999)
        self.assertEqual(result.outcome, "player-death")
        self.assertEqual([(row["event"], row["stop"]) for row in self.rows()],
                         [("counts", "<player-death> feature=あなたは死にました。")])

    def test_write_failures_are_swallowed(self):
        self.path.mkdir()   # a directory where the log should be
        shadow = InputContextShadow(self.path)
        observed = current_input_state(with_context(prompt_screen(DEPARTURE_QUESTION), COMMAND))
        shadow.observe("melee", observed, prompt_screen(DEPARTURE_QUESTION), screen_only=True)
        shadow.stop("<stuck-prompt> x")
        self.assertEqual(shadow.write_failures, 2)
        self.assertEqual(shadow.disagreements, {"command": 1})

    def test_rotates_itself_with_one_predecessor(self):
        shadow = InputContextShadow(self.path, rotate_bytes=200)
        for _ in range(6):
            shadow.stop("<stuck-prompt> " + "x" * 120)
        self.assertTrue(self.path.with_name(self.path.name + ".1").exists())
        self.assertFalse(self.path.with_name(self.path.name + ".2").exists())
        self.assertLess(self.path.stat().st_size, 600)


if __name__ == "__main__":
    unittest.main()
