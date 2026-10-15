"""Pins the delayed headless character-dump continuation through the executor."""

import tests  # noqa: F401

import gzip
import json
import unittest
from pathlib import Path

from hengbot.control_client import ControlClient
from hengbot.input_executor import (
    Continuation, Operation, OperationExecutor, ScreenKind, ScreenMatch,
)


FIXTURE = Path(__file__).with_name("fixtures") / "headless-character-dump-20261016.jsonl.gz"


def _fixture_rows():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def _constructed_screen(width, height, *, row0="", footer="", footer_row=None):
    # DECLARED CONSTRUCTED: only the recorded prompt rows are placed in this
    # minimal screen frame; the capture does not contain raw control screens.
    screen = {"width": width, "height": height, "lines": [""] * height}
    screen["lines"][0] = row0
    screen["lines"][height - 1 if footer_row is None else footer_row] = footer
    return screen


def _command_screen(turn=1):
    screen = _constructed_screen(80, 24)
    screen["cursor"] = {"visible": False, "y": 10, "x": 20}
    screen["turn"] = turn
    screen["lines"][1] = "Human"
    screen["lines"][10] = " " * 20 + "@"
    screen["lines"][23] = " " * 72 + "Surf."
    return screen


class _ScriptedGame:
    """Protocol peer that holds a screen until its separately posted key takes effect."""

    def __init__(self, sheet, filename, *, stale_after_f):
        self.sheet = sheet
        self.filename = filename
        self.stale_after_f = stale_after_f
        self.accepted = []
        self.reads_after_f = 0

    def socket_factory(self, *_args, **_kwargs):
        return _ScriptedSocket(self)

    def screen(self):
        last = self.accepted[-1] if self.accepted else ""
        if last == "C":
            return self.sheet
        if last == "f":
            self.reads_after_f += 1
            return self.sheet if self.stale_after_f and self.reads_after_f == 1 else self.filename
        if last == "\r":
            return self.sheet
        if last == "\x1b":
            return _command_screen(2)
        if last == "x":
            return self.sheet
        return _command_screen()

    def handle(self, request):
        op = request["op"]
        if op == "keys":
            posted = request["keys"].replace(r"\r", "\r").replace(r"\e", "\x1b")
            self.accepted.append(posted)
            result = {"pushed": len(posted)}
        elif op == "screen":
            result = self.screen()
        elif op == "state":
            result = {
                "turn": 2, "floor": {"dungeon_id": 0, "level": 0},
                "player": {"gold": 0}, "inventory": [], "equipment": [],
                "grid_map": {"runs": []}, "messages": [],
            }
        else:
            result = {"turn": 2}
        return {"id": request["id"], "ok": True, "result": result}


class _ScriptedSocket:
    def __init__(self, game):
        self.game = game
        self.output = bytearray()

    def settimeout(self, _value):
        pass

    def close(self):
        pass

    def sendall(self, payload):
        response = self.game.handle(json.loads(payload))
        self.output.extend((json.dumps(response, ensure_ascii=False) + "\n").encode())

    def recv(self, size):
        amount = min(size, len(self.output))
        result = bytes(self.output[:amount])
        del self.output[:amount]
        return result


class HeadlessCharacterDumpContinuationTest(unittest.TestCase):
    def make(self, sheet, filename, *, stale_after_f):
        game = _ScriptedGame(sheet, filename, stale_after_f=stale_after_f)
        client = ControlClient(
            1, request_budget=2, retries=1, backoff=0,
            socket_factory=game.socket_factory)
        self.addCleanup(client.close)
        executor = OperationExecutor(client, drain=lambda: [])
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        return game, executor

    def test_captured_sheet_waits_for_posted_dump_keys_then_closes(self):
        rows = _fixture_rows()
        sheet = _constructed_screen(
            80, 24, footer=rows[0]["character_footer"])
        filename = _constructed_screen(
            80, 24, row0=rows[1]["file_name_prompt"],
            footer=rows[0]["character_footer"])
        game, executor = self.make(sheet, filename, stale_after_f=True)
        operation = Operation(
            1, "periodic:character-dump", "C", executor.ready_board,
            continuations=[
                Continuation(frozenset({ScreenKind.CHARACTER}), "f"),
                Continuation(frozenset({ScreenKind.FILE_NAME}), "\r"),
                Continuation(frozenset({ScreenKind.CONFIRM}), "y", optional=True),
                Continuation(frozenset({ScreenKind.CHARACTER}), "\x1b"),
            ],
            response_grace=3.0,
        )
        result = executor.submit(operation, deadline=9999999999)
        self.assertEqual(result.outcome, "completed", result.reason)
        self.assertEqual(game.accepted, ["C", "f", "\r", "\x1b"])
        self.assertEqual(result.screen.kind, ScreenKind.COMMAND)

    def test_character_sheet_without_dump_owner_remains_stuck(self):
        rows = _fixture_rows()
        sheet = _constructed_screen(
            80, 24, footer=rows[0]["character_footer"])
        game, executor = self.make(sheet, _command_screen(), stale_after_f=False)
        result = executor.submit(Operation(
            2, "unrelated", "x", executor.ready_board),
            deadline=9999999999)
        self.assertEqual(result.outcome, "stuck-prompt")
        self.assertIn("unowned character:", result.reason)
        self.assertEqual(game.accepted, ["x"])

    def test_large_terminal_dump_has_no_stale_sheet_wait(self):
        rows = _fixture_rows()
        sheet = _constructed_screen(
            211, 67, footer=" " * 65 + rows[0]["character_footer"], footer_row=44)
        filename = _constructed_screen(
            211, 67, footer=" " * 65 + rows[0]["character_footer"], footer_row=44)
        filename["lines"][21] = " " * 65 + rows[1]["file_name_prompt"]
        game, executor = self.make(sheet, filename, stale_after_f=False)
        operation = Operation(
            3, "periodic:character-dump", "C", executor.ready_board,
            continuations=[
                Continuation(frozenset({ScreenKind.CHARACTER}), "f"),
                Continuation(frozenset({ScreenKind.FILE_NAME}), "\r"),
                Continuation(frozenset({ScreenKind.CHARACTER}), "\x1b"),
            ], response_grace=3.0)
        result = executor.submit(operation, deadline=9999999999)
        self.assertEqual(result.outcome, "completed", result.reason)
        self.assertEqual(game.accepted, ["C", "f", "\r", "\x1b"])
        self.assertEqual(result.screen.kind, ScreenKind.COMMAND)


if __name__ == "__main__":
    unittest.main()
