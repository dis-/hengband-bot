"""Recorded Q34 board; source-derived power waits, not a live-game replay."""

import tests  # noqa: F401 -- isolate runtime files
import json
from pathlib import Path
import unittest

import test_input_executor as inputs
import test_magic_eater_o3 as o3
from test_magic_eater_o3 import powers, prompt
from hengbot.cli import _ExecutorInputPort, SendResult
from hengbot.control_client import ControlClient
from hengbot.input_executor import OperationExecutor
from hengbot.magic_eater import MISSILE_REASON
from hengbot.model import parse_snapshot


class PowerGame(inputs.FaithfulHookGame):
    """cmd-magiceat.cpp non-menu choices: reject unknown/empty slot selection."""

    def __init__(self, board, charges):
        super().__init__()
        self.state = board
        self.charges = charges
        self.wait = "command"
        self.fired = 0
        self.thrown = 0

    def _consume(self, *, pump_frontend=True):
        raw = "".join(self.term_fifo)
        if not raw:
            return super()._consume(pump_frontend=pump_frontend)
        if self.wait == "command":
            if raw == "vb6":
                torch = next(item for item in self.state["inventory"] if item["slot"] == "b")
                assert (torch["tval"], torch["sval"]) == (39, 0) and torch["count"] > 0
                self.thrown += 1
                screen = inputs.command_screen(self.state["turn"] + 1)
            else:
                assert raw == "m", raw
                self.wait = "type"
                screen = prompt("[A] staff, [B] wand, [C] rod:")
        elif self.wait == "type":
            assert raw == "B", raw
            self.wait = "power"
            screen = prompt("(*=List, ESC=exit) Use which power? ", "spell")
        elif self.wait == "power":
            if raw == "\x1b":
                self.wait = "command"
                screen = inputs.command_screen(self.state["turn"])
            elif raw == "*":
                screen = powers(self.charges or 0)
                if self.charges is None:
                    # A different learned wand keeps this type's menu open.
                    screen["lines"][17] = ""
                    screen["lines"][2] = "a) Heal Monster                 1/1  35%"
            else:
                assert raw == "p" and self.charges and self.charges > 0, raw
                self.wait = "aim"
                screen = prompt("Direction?", "direction", can_choose_target=True)
        else:
            assert self.wait == "aim" and raw == "6", (self.wait, raw)
            self.fired += 1
            self.charges -= 1
            self.wait = "command"
            screen = inputs.command_screen(self.state["turn"] + 1)
        self.screens = [screen]
        self.states = [dict(self.state, turn=self.state["turn"] + (self.fired + self.thrown > 0))]
        return super()._consume(pump_frontend=pump_frontend)


class RecordedRangedFireTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        o3.MagicEaterO3Test.setUpClass()

    def run_captured(self, charges):
        raw = json.loads((Path(__file__).parent / "fixtures" /
                          "me-q34-ranged-fire-1029.json").read_text(encoding="utf-8"))
        policy = o3.MagicEaterO3Test().policy()
        # Constructed knowledge prerequisite: protocol 3 omits these two skills.
        policy._skill_exp_cache = (0, 0, 1, None)
        board = parse_snapshot(raw, policy._monrace_knowledge)
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), ("mBp6", MISSILE_REASON))
        game = PowerGame(raw, charges)
        client = ControlClient(1, request_budget=2, retries=1, backoff=0,
                               socket_factory=game.socket_factory)
        self.addCleanup(client.close)
        executor = OperationExecutor(client, drain=lambda: list(game.jsonl))
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason, "sequence": 1}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual(game.wait, "command")
        return game, policy, parse_snapshot(port.last_result.board, policy._monrace_knowledge), port

    def test_captured_board_fires_a_charged_absorbed_missile(self):
        game, _, _, _ = self.run_captured(17)
        self.assertEqual((game.fired, game.charges), (1, 16))
        self.assertEqual(game.accepted, ["m", "B", "*", "p", "6"])

    def test_empty_and_missing_missile_close_prompt_and_choose_approved_throw(self):
        for charges in (0, None):
            with self.subTest(charges=charges):
                game, policy, observed, port = self.run_captured(charges)
                self.assertEqual(game.fired, 0)
                self.assertEqual(game.accepted, ["m", "B", "*", "\x1b"])
                self.assertEqual(observed.magic_eater_wand_charges, 0)
                key = policy.choose_key(observed)
                self.assertEqual(key, "vb6")
                self.assertEqual(policy.last_reason, "quest-strategy:throw-torch")
                self.assertEqual(port(key, decision={"reason": policy.last_reason, "sequence": 2}),
                                 SendResult.SENT, port.last_result.reason)
                self.assertEqual((game.thrown, game.wait), (1, "command"))

    def test_legacy_command_char_power_context_remains_supported(self):
        helper = o3.MagicEaterO3Test()
        self.addCleanup(helper.doCleanups)
        power = powers(1)
        power["input_context"]["kind"] = "command_char"
        game, result, status = helper.run_follow("mBp6", MISSILE_REASON, [
            prompt("[A] staff, [B] wand, [C] rod:"), power,
            prompt("Direction?", "direction", can_choose_target=True)])
        self.assertEqual(status, SendResult.SENT, result.reason)
        self.assertEqual(game.accepted, ["m", "B", "p", "6"])

    def test_rejected_power_closes_prompt_instead_of_leaving_aim_pending(self):
        helper = o3.MagicEaterO3Test()
        self.addCleanup(helper.doCleanups)
        game, result, status = helper.run_follow("mBp6", MISSILE_REASON, [
            prompt("[A] staff, [B] wand, [C] rod:"), powers(1), powers(0)])
        self.assertEqual(status, SendResult.SENT, result.reason)
        self.assertEqual(game.accepted, ["m", "B", "p", "\x1b"])
        self.assertEqual(result.board["_magic_eater_wand_charges"], 0)
