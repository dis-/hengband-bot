"""Issue #47: a centered dump message owns MORE before the sheet's exit.

Linux stops/preamble are unmodified captures. Windows wait screens were
measured separately with the same Magic-Eater save and the warrior template.
The peer below models cmd-draw.cpp -> files-util.cpp -> msg_flush; it changes
state only when an input accepted by that source wait is posted.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import hashlib
import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot.cli import (
    _consume_response_sequence, _ExecutorInputPort, _send_new_decision_key,
    SendResult,
)
from hengbot.control_client import ControlClient
from hengbot.input_executor import classify_screen, OperationExecutor, ScreenKind
from hengbot.policy import HengbotPolicy
import test_headless_character_dump as protocol


FIXTURE = Path(__file__).with_name("fixtures") / "me-dump-stuck-20261029.json.gz"
SHA256 = "19623f10a8cf62f7c3d6bd10f92833d8dd4322ea62537bfada673d78089ed26c"


class DumpPeer:
    """Source-derived peer: keep the sheet underneath the success message."""

    def __init__(self, rows, *, stop=None, overwrite=True):
        self.rows = rows
        self.stop = stop
        self.overwrite = overwrite
        self.accepted = []
        self.phase = "command"

    def handle(self, request):
        if request["op"] == "keys":
            key = request["keys"].replace(r"\r", "\r").replace(r"\e", "\x1b").replace(r"\s", " ")
            transitions = {
                ("command", "C"): "sheet", ("sheet", "f"): "filename",
                ("filename", "\r"): "confirm" if self.overwrite else "success",
                ("confirm", "y"): "success", ("success", " "): "return",
                ("return", "\x1b"): "done",
            }
            # With skip_more the source returns directly to the sheet.
            if (self.phase, key) == ("success", "\x1b"):
                has_more = self.rows[13]["screen"].get("input_context") is not None
                self.phase = "return" if has_more else "done"
            else:
                self.phase = transitions[self.phase, key]
            self.accepted.append(key)
            result = {"pushed": len(key)}
        else:
            index = {"command": 9, "sheet": 10, "filename": 11, "confirm": 12,
                     "success": 13, "return": 14, "done": 15}[self.phase]
            row = self.stop if self.stop is not None and self.phase == "return" else self.rows[index]
            result = row["screen" if request["op"] == "screen" else "state"]
        return {"id": request["id"], "ok": True, "result": result}

    def socket_factory(self, *_args, **_kwargs):
        return protocol._ScriptedSocket(self)


class CharacterDumpMoreRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == SHA256
        cls.data = json.loads(gzip.decompress(FIXTURE.read_bytes()))

    def send_dump(self, peer, key, policy=None, snapshot=None):
        client = ControlClient(1, request_budget=2, retries=1, backoff=0,
                               socket_factory=peer.socket_factory)
        self.addCleanup(client.close)
        executor = OperationExecutor(client, drain=lambda: [])
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 3).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=False,
                                  request_budget=3, policy=policy)
        sent, _ = _send_new_decision_key(
            port, "captured-command", key, None, set(), in_store=False,
            snapshot=snapshot, decision={"sequence": 3, "reason": "periodic:character-dump", "key": key})
        self.assertEqual(sent, SendResult.SENT, port.last_result.reason)
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual(port.last_result.screen.kind, ScreenKind.COMMAND)
        self.assertIsNone(executor.active)
        self.assertEqual(peer.phase, "done")

    def test_public_choose_and_follow_replay_both_linux_stops_to_map(self):
        policy = HengbotPolicy()
        policy.request_character_dump()
        policy.request_game_save()
        with TemporaryDirectory() as directory:
            lines = [json.dumps(row) + "\n" for row in self.data["linux_preamble"]]
            expected = ["~f\x1b", "~9\x1b\x1b", "\x13", "Cf\ry\x1b\x1b"]
            for indices, expected_key in zip(([0], [1, 2], [3, 4], [5]), expected):
                _, boards = _consume_response_sequence(
                    [lines[i] for i in indices], policy, lambda _: True, {},
                    knowledge_ledger_path=Path(directory) / "knowledge.jsonl")
                key = policy.choose_key(boards[-1])
                self.assertEqual(key, expected_key)
                policy.confirm_key_posted(key)
            self.assertEqual(policy.last_reason, "periodic:character-dump")
            for stop in self.data["linux_stops"]:
                with self.subTest(stop_time=stop["screen"]["lines"][42].strip()):
                    peer = DumpPeer(self.data["measured"]["magic_eater"], stop=stop)
                    self.send_dump(peer, key, policy, boards[-1])
                    self.assertEqual(peer.accepted, ["C", "f", "\r", "y", " ", "\x1b"])

    def test_original_warrior_control_keeps_its_five_segments(self):
        peer = DumpPeer(self.data["measured"]["warrior_template"])
        self.send_dump(peer, "Cf\ry\x1b\x1b")
        self.assertEqual(peer.accepted, self.data["warrior_control_keys"])

    def test_first_dump_without_existing_file_still_owns_success_more(self):
        peer = DumpPeer(self.data["measured"]["magic_eater"], overwrite=False)
        self.send_dump(peer, "Cf\ry\x1b\x1b")
        self.assertEqual(peer.accepted, ["C", "f", "\r", " ", "\x1b"])

    def test_centered_more_uses_same_rendered_origin_in_both_languages(self):
        measured = self.data["measured"]["magic_eater"][13]["screen"]
        for literal in ("-続く-", "-more-"):
            for context in (None, {"kind": "more", "prompt": literal}):
                with self.subTest(literal=literal, context=context):
                    screen = copy.deepcopy(measured)
                    screen["input_context"] = context
                    screen["lines"][22] = " " * 66 + "Dump successful." + literal
                    match = classify_screen(screen)
                    self.assertEqual((match.kind, match.feature, match.row, match.column),
                                     (ScreenKind.MORE, literal, 22, 82))

    def test_more_text_without_character_footer_is_not_a_centered_prompt(self):
        screen = copy.deepcopy(self.data["measured"]["magic_eater"][13]["screen"])
        screen["lines"][45] = ""
        self.assertNotEqual(classify_screen(screen).kind, ScreenKind.MORE)


if __name__ == "__main__":
    unittest.main()
