"""A failed absorbed Identify whose message the monsters' turn overwrote ends the use (n1-b life-397).

n1-b life-397 2026-11-14 17:24 (Magic-Eater Lv47, 49F of dungeon 12, build d7356e57ae)
identified a picked-up スプリント・メイル with the absorbed Identify ('mAfl',
identify:dungeon-equipment).  cmd-magiceat.cpp: the use failed (「呪文をうまく唱えられなかった！」,
a player turn spent, no item asked), and in the same game turn a unique fought an unseen
monster next to the character, so the screen's message line showed the monsters' messages,
not the failure.  The Magic-Eater stepper (magic_eater_input.AbsorbedUseMenu) waited for the
Identify item prompt at its ``target`` stage; the command screen was not a stage it expected
the game to skip (``unasked_stages`` held ``aim`` only), so the operation stopped
``<stuck-prompt> ... reason=unowned Magic-Eater identify prompt``.

Fix: the item prompt is asked only after the use succeeds, like the direction: ``target`` is
an unasked stage of the absorbed staff powers too (me_device_attacks_input already has it),
so the command screen ends the use as failed:magic-eater and the next decision decides again.

Recorded: the stop's control-port screen and state, the decided key and the characters the
bot posted for it (tests/extract_n1b_397_me_identify_fail_1114_fixture.py), posted through
the production executor (``_ExecutorInputPort``).
DECLARED CONSTRUCTED: the two screens before the failure (the kind question and the staff
power list with the Identify row, as tests/test_me_staff_sequence.py builds them); the
stepper's answers to them are the recorded posted characters.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import unittest
from pathlib import Path

from hengbot.cli import SendResult, _ExecutorInputPort
from hengbot.control_client import ControlClient
from hengbot.input_executor import OperationExecutor
from hengbot.model import SV_STAFF_IDENTIFY
from tests.support import recorded as harness
from tests.test_magic_eater_o3 import prompt
from tests.test_me_staff_sequence import power_list

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-397-me-identify-fail-1114.json.xz"
FAILED_USE = "呪文をうまく唱えられなかった！"


class N1b397MeIdentifyFail1114RecordedTest(harness.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        cls.case = json.loads(lzma.decompress(FIXTURE.read_bytes()))

    def test_recorded_stop(self):
        case = self.case
        self.assertEqual((case["decision"]["key"], case["decision"]["reason"]),
                         ("mAfl", "identify:dungeon-equipment"))
        self.assertEqual(case["posted"], ["m", "A", "f"])
        self.assertTrue(case["stuck_line"].endswith("reason=unowned Magic-Eater identify prompt"))
        # The use failed; the monsters' messages came after it in the same game turn.
        messages = case["stop_state"]["messages"]
        self.assertIn(FAILED_USE, messages)
        self.assertNotEqual(messages[-1], FAILED_USE)
        screen = case["stop_screen"]
        self.assertEqual(screen["input_context"]["kind"], "command")
        self.assertFalse(any(FAILED_USE in line for line in screen["lines"]))
        target = next(item for item in case["stop_state"]["inventory"] if item["slot"] == "l")
        self.assertFalse(target["known"])

    def test_command_screen_after_the_power_ends_the_failed_use(self):
        case = self.case
        game = harness.FaithfulHookGame()
        game.state = dict(copy.deepcopy(case["stop_state"]), grid_map={"runs": []})
        game.state["turn"] -= 1
        client = ControlClient(1, request_budget=2, retries=1, backoff=0,
                               socket_factory=game.socket_factory)
        self.addCleanup(client.close)
        executor = OperationExecutor(client, drain=lambda: list(game.jsonl))
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        game.screens = [prompt("[A] 杖, [B] 魔法棒, [C] ロッド:"),
                        power_list(SV_STAFF_IDENTIFY, 8, 10),
                        copy.deepcopy(case["stop_screen"]),
                        harness.command_screen(case["stop_state"]["turn"])]
        game.states = [copy.deepcopy(case["stop_state"]) for _ in game.screens]
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        status = port(case["decision"]["key"],
                      decision={"reason": case["decision"]["reason"], "sequence": 1})
        # Recorded: TERMINAL, <stuck-prompt> unowned Magic-Eater identify prompt.
        self.assertEqual(status, SendResult.SENT, port.last_result.reason)
        self.assertEqual(game.accepted, case["posted"])
        self.assertEqual(port.last_result.operation.business_outcome, "failed:magic-eater")


if __name__ == "__main__":
    unittest.main()
