"""Public Q34 choices and production follow input, with source-derived rests."""

import tests  # noqa: F401
from dataclasses import replace
import unittest

import test_input_executor as inputs
import test_magic_eater_o3 as o3
from test_magic_eater_o3 import prompt
import test_magic_eater_ranged_fire_recorded as recorded
from hengbot.cli import SendResult
from hengbot.magic_eater import MISSILE_REASON
from hengbot.model import parse_snapshot


class RechargeGame(recorded.PowerGame):
    recovered = 1
    refused = False
    interrupted = False
    silent = False
    japanese = False

    def _consume(self, *, pump_frontend=True):
        raw = "".join(self.term_fifo)
        if not ((self.wait == "command" and raw == "R") or self.wait == "rest"):
            return super()._consume(pump_frontend=pump_frontend)
        if self.wait == "command" and not self.refused:
            self.wait = "rest"
            text = ("休憩 (0-9999, '*' で HP/MP全快, '&' で必要なだけ): "
                    if self.japanese else "Rest (0-9999, '*' for HP/SP, '&' as needed): ")
            screen = prompt(text, "quantity")
        else:
            if not self.refused:
                assert raw == "100\r", raw
                self.state = dict(self.state, turn=self.state["turn"] +
                                  (10 if self.interrupted else 1000))
                self.charges = self.recovered
                if self.interrupted and not self.silent:
                    self.state["messages"] = ["中断しました。" if self.japanese else "Canceled."]
            self.wait = "command"
            screen = inputs.command_screen(self.state["turn"])
        self.screens = [screen]
        self.states = [dict(self.state)]
        return inputs.FaithfulHookGame._consume(self, pump_frontend=pump_frontend)


class RechargeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        o3.MagicEaterO3Test.setUpClass()

    def start(self, **settings):
        helper = recorded.RecordedRangedFireTest()
        self.addCleanup(helper.doCleanups)
        game_type = type("ConfiguredRechargeGame", (RechargeGame,), settings)
        return helper.run_captured(0, game_type)

    def send_choice(self, game, policy, board, port, expected, sequence):
        key = policy.choose_key(board)
        self.assertEqual(key, expected)
        self.assertEqual(port(key, decision={"reason": policy.last_reason, "sequence": sequence}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual(game.wait, "command")
        return parse_snapshot(port.last_result.board, policy._monrace_knowledge)

    def test_used_up_rest_100_recheck_and_fire_in_both_languages(self):
        for japanese in (False, True):
            with self.subTest(japanese=japanese):
                game, policy, board, port = self.start(japanese=japanese)
                board = self.send_choice(game, policy, board, port, "R100\r", 2)
                self.assertEqual(game.accepted[-2:], ["R", "100\r"])
                self.assertEqual(board.turn, 77642)
                self.send_choice(game, policy, board, port, "mBp6", 3)
                self.assertEqual((game.fired, game.charges), (1, 0))
                self.assertEqual(game.accepted[-5:], ["m", "B", "*", "p", "6"])

    def test_refusal_and_interruption_fall_back_even_if_charge_recovers(self):
        for settings in ({"refused": True}, {"interrupted": True},
                         {"interrupted": True, "japanese": True},
                         {"interrupted": True, "silent": True}):
            with self.subTest(settings=settings):
                game, policy, board, port = self.start(**settings)
                board = self.send_choice(game, policy, board, port, "R100\r", 2)
                self.send_choice(game, policy, board, port, "vb6", 3)
                self.assertEqual((game.fired, game.thrown), (0, 1))

    def test_no_recovery_rechecks_then_throws_and_never_rests_again(self):
        game, policy, board, port = self.start(recovered=0)
        board = self.send_choice(game, policy, board, port, "R100\r", 2)
        board = self.send_choice(game, policy, board, port, "mBp6", 3)
        board = self.send_choice(game, policy, board, port, "vb6", 4)
        for sequence in range(5, 11):
            key = policy.choose_key(board)
            self.assertNotEqual(key, "R100\r")
            board = self.send_choice(game, policy, board, port, key, sequence)
        self.assertEqual(game.accepted.count("R"), 1)
        self.assertEqual(game.fired, 0)

    def test_rest_safety_rejects_status_mobile_threat_and_fixed_adjacency(self):
        helper = o3.MagicEaterO3Test()
        for unsafe in ("hungry", "injured", "afraid", "mobile", "adjacent"):
            with self.subTest(unsafe=unsafe):
                board = helper.board(charges=0)
                if unsafe in {"hungry", "injured", "afraid"}:
                    fields = {"food_state": "hungry"} if unsafe == "hungry" else (
                        {"hp": 99} if unsafe == "injured" else {"afraid": True})
                    board = replace(board, player=replace(board.player, **fields))
                else:
                    monster = replace(board.visible_monsters[0],
                                      race_id=174 if unsafe == "mobile" else 243,
                                      position=replace(board.player.position, x=12))
                    board = replace(board, visible_monsters=[*board.visible_monsters, monster])
                policy = helper.policy()
                self.assertNotEqual(policy.choose_key(board), "R100\r")

    def test_upper_room_bee_does_not_prevent_safe_stand_rest(self):
        helper = o3.MagicEaterO3Test()
        board = helper.board(charges=0)
        bee = replace(board.visible_monsters[0], race_id=174,
                      position=replace(board.player.position, y=3, x=13))
        policy = helper.policy()
        self.assertEqual(policy.choose_key(replace(
            board, visible_monsters=[*board.visible_monsters, bee])), "R100\r")
        self.assertEqual(policy.last_reason, MISSILE_REASON)
