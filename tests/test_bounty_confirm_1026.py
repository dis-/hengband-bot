"""Issue #47: recorded text/state; explicitly source-derived modal screens.

The archive has NO screen captures or accepted-key replies. Geometry and
post-divergence effects below are CONSTRUCTED from the cited C++ call path.
No claim is made that the constructed success was observed on the live game.
"""
import tests  # noqa: F401
import copy
import json
from pathlib import Path
import unittest

from hengbot.cli import _ExecutorInputPort, _send_new_decision_key, SendResult
from hengbot.input_executor import ScreenKind, classify_screen
import tests.test_input_executor as executor_harness
from tests.test_input_executor import FaithfulHookGame, command_screen


def evidence():
    return json.loads((Path(__file__).parent / "fixtures" /
                       "bounty-confirm-1026.json").read_text(encoding="utf-8"))


def building_screen(prompt="", width=198, height=48):
    # CONSTRUCTED: building-service.cpp:89,109,144; cmd-building.cpp:342.
    ox, oy = (width - 80) // 2, (height - 24) // 2
    lines = [""] * height
    lines[oy] = " " * ox + prompt
    lines[oy + 2] = " " * ox + " Hunter (Human) Hunter's office"
    lines[oy + 19] = " " * ox + " c) 換金する"
    lines[oy + 23] = " " * ox + " ESC) 建物を出る"
    return {"width": width, "height": height, "lines": lines,
            "cursor": {"visible": True, "x": ox, "y": oy}}


class BountyHookGame(FaithfulHookGame):
    """CONSTRUCTED exchange_cash interpreter on the existing FIFO harness.

    One item, no JSONL inside the building. y consumes the remain; ESC in
    input_check means no; msg_erase MORE consumes a separate key.
    """
    def __init__(self, *, refused=False, width=198, height=48, prompt=None,
                 entry_more=False, no_offer=False, result_more=False):
        super().__init__()
        self.evidence = evidence()
        self.state = copy.deepcopy(self.evidence["board"])
        self.state["player"].update(y=26, x=71)
        self.state["messages"] = []
        self.phase = "command"
        self.refused, self.width, self.height = refused, width, height
        self.question = prompt or self.evidence["prompt"]
        self.entry_more = entry_more
        self.no_offer = no_offer
        self.result_more = result_more
        self.waits = []
        self.answers = []

    def _consume(self, *, pump_frontend=True):
        if pump_frontend:
            self.term_fifo.extend(self.frontend_fifo)
            self.frontend_fifo.clear()
        raw = "".join(self.term_fifo)
        self.term_fifo.clear()
        for key in raw:
            self.waits.append((self.phase, key))
            if self.phase == "command" and key == "8":
                self.state["player"].update(y=25, x=71)
                self.phase = "entry-more" if self.entry_more else "building"
            elif self.phase == "entry-more" and key in " \x1b":
                self.phase = "building"
            elif self.phase == "building" and key == "c":
                self.phase = ("result-more" if self.result_more else "building") if self.no_offer else "confirm"
                if self.no_offer:
                    self.state["messages"] = [self.evidence["refusal"]]
            elif self.phase == "confirm":
                self.answers.append(key)
                if key == "y" and not self.refused:
                    self.state["inventory"] = []
                    # bounty.cpp permanent rewards do not set change=true:
                    # the misleading "nothing" text is possible even on success.
                    self.state["messages"] = ["これで合計 1 ポイント獲得しました。",
                                              self.evidence["refusal"]]
                else:
                    self.state["messages"] = [self.question, self.evidence["refusal"]]
                self.phase = "result-more" if self.result_more else "building"
            elif self.phase == "result-more" and key in " \x1b":
                self.phase = "building"
            elif self.phase == "building" and key == "\x1b":
                self.phase = "command"
                self.state["turn"] += 1
            else:
                raise AssertionError((self.phase, key))
        if self.phase == "command":
            self.screen = command_screen(self.state["turn"])
            self.jsonl.append(copy.deepcopy(self.state))
        else:
            prompt = self.question if self.phase == "confirm" else (
                "賞金窓口 -続く-" if self.phase.endswith("more") else "")
            self.screen = building_screen(prompt, self.width, self.height)


class BountyConfirmPins(executor_harness.ProductionHarness):
    def test_recorded_before_cashout_keeps_remain_and_returns_to_same_cell(self):
        recorded = evidence()
        rows = recorded["decisions"]
        self.assertEqual([r["key"] for r in rows], ["8cy\x1b", "2", "8cy\x1b"])
        self.assertEqual(rows[0]["position"], rows[2]["position"])
        self.assertEqual(rows[1]["turn"], recorded["board"]["turn"])
        self.assertEqual(rows[1]["position"], {"y": 25, "x": 71})
        self.assertTrue(recorded["board"]["inventory"][0]["is_bounty"])
        self.assertEqual([r["segments"] for r in rows], [4, 1, 4])
        self.assertEqual(rows[0]["requests"], [
            "keys", "screen", "state", "keys", "screen", "state",
            "keys", "screen", "keys", "screen", "state"])

    def send(self, game):
        game, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=False, request_budget=2)
        sent, _ = _send_new_decision_key(
            port, "recorded-projection", "8cy\x1b", None, set(), in_store=False,
            decision={"sequence": 12939, "reason": "bounty:cashout"})
        return sent, port, executor

    def test_centered_recorded_question_precedes_persistent_menu(self):
        match = classify_screen(building_screen(evidence()["prompt"]))
        self.assertEqual((match.kind, match.feature, match.row),
                         (ScreenKind.CONFIRM, evidence()["prompt"], 12))
        self.assertEqual(classify_screen(building_screen("窓口 -続く-")).kind,
                         ScreenKind.MORE)
        self.assertEqual(classify_screen(building_screen()).kind, ScreenKind.BUILDING)

    def test_follow_executor_answers_observed_question_and_hands_over(self):
        for width, height in ((198, 48), (198, 24), (80, 48), (80, 24), (81, 25)):
            with self.subTest(width=width, height=height):
                game = BountyHookGame(width=width, height=height)
                sent, port, executor = self.send(game)
                self.assertEqual(sent, SendResult.SENT)
                self.assertEqual(game.accepted, ["8", "c", "y", "\x1b"])
                self.assertEqual(game.answers, ["y"])
                self.assertEqual(executor.ready_board["inventory"], [])
                self.assertEqual(port.last_result.outcome, "completed")

    def test_more_before_question_never_spends_yes(self):
        game = BountyHookGame(entry_more=True, result_more=True)
        sent, _, _ = self.send(game)
        self.assertEqual(sent, SendResult.SENT)
        self.assertEqual(game.accepted, ["8", " ", "c", "y", " ", "\x1b"])
        self.assertIn(("confirm", "y"), game.waits)

    def test_refused_handover_is_named_terminal_before_another_decision(self):
        game = BountyHookGame(refused=True)
        sent, port, executor = self.send(game)
        self.assertEqual(sent, SendResult.TERMINAL)
        self.assertEqual(game.accepted, ["8", "c", "y", "\x1b"])
        self.assertIn("bounty-handover-refused", port.last_result.stop_line)
        self.assertIsNone(executor.ready_board)
        self.assertTrue(game.state["inventory"][0]["is_bounty"])

    def test_no_current_offer_closes_without_sending_yes_or_reentering(self):
        game = BountyHookGame(no_offer=True)
        sent, port, _ = self.send(game)
        self.assertEqual(sent, SendResult.TERMINAL)
        self.assertEqual(game.accepted, ["8", "c", "\x1b"])
        self.assertEqual(game.answers, [])
        self.assertIn("bounty-handover-refused", port.last_result.stop_line)

    def test_other_centered_question_cannot_receive_bounty_yes(self):
        game = BountyHookGame(prompt="関係ない質問？[y/n]")
        sent, port, _ = self.send(game)
        self.assertEqual(sent, SendResult.TERMINAL)
        self.assertEqual(game.accepted, ["8", "c"])
        self.assertIn("unowned confirm", port.last_result.reason)
        self.assertEqual(game.answers, [])

    def test_english_handover_uses_the_same_observed_continuation(self):
        game = BountyHookGame(prompt="Hand Borshin corpse over? [y/n]")
        sent, _, _ = self.send(game)
        self.assertEqual(sent, SendResult.SENT)
        self.assertEqual(game.answers, ["y"])


if __name__ == "__main__":
    unittest.main()
