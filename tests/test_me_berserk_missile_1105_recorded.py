"""n1-c life-143, Orc cave 23F, 2026-11-05 18:01: ``mBp2`` while berserk.

A rage mutation's fit made the Lv44 Magic-Eater berserk.  A swallow stood beside
it and the adjacent chooser fired the absorbed Magic Missile (``mBp`` + direction;
the reason quest-strategy:ranged-fire:magic-eater is that missile's fixed label).
input-key-processor.cpp refuses ``m`` while berserk with no turn passing, so the
kind question never came; the menu walk stopped as a stuck prompt.  The board did
not change, so each restart chose the same key.  Fixture:
tests/extract_me_berserk_missile_1105_fixture.py.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.model import parse_snapshot
from test_hourly_0700_1102_recorded import RecordedTownPolicy
from tests.support import recorded as executor_pins


FIXTURE = Path(__file__).with_name("fixtures") / "me-berserk-missile-20261105.json.gz"
MISSILE = ("mBp2", "quest-strategy:ranged-fire:magic-eater")


class MagicCommandRefusedRecordedTest(RecordedTownPolicy, executor_pins.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)

    def post(self, raw, key, reason, answer, after):
        """``key`` from ``raw`` through the production port; ``answer`` and
        ``after`` are the screen and state the game shows next."""
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = [copy.deepcopy(answer)]
        game.states = [copy.deepcopy(after)]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": 1, "reason": reason},
            snapshot=parse_snapshot(copy.deepcopy(raw), self.monrace),
            posting_contract=PostingContract())
        return game, port, sent

    def test_the_fixture_is_the_recorded_stop(self):
        recorded = self.case["decisions"][-1]
        self.assertEqual((recorded["key"], recorded["reason"]), MISSILE)
        self.assertEqual(self.case["board"]["floor"]["quest_id"], 0)
        self.assertEqual(self.case["board"]["player"]["status_bar"][0]["key"], "berserk")
        self.assertIn("狂戦士化していて頭が回らない！", self.case["stop_screen"]["lines"][0])

    def test_berserk_answers_the_swallow_without_the_refused_command(self):
        raw = self.case["board"]
        policy = self.primed(raw, [], self.case["skill"])
        key = policy.choose_key(self.board(policy, raw))
        self.assertEqual((key, policy.last_reason), ("2", "melee"))
        # DECLARED CONSTRUCTED: the game's reply to the blow, its turn advanced.
        after = {**copy.deepcopy(raw), "turn": raw["turn"] + 10}
        game, port, sent = self.post(raw, key, policy.last_reason,
                                     executor_pins.command_screen(after["turn"]), after)
        self.assertTrue(sent, port.last_result.reason)
        self.assertEqual(game.accepted, ["2"])

    def test_a_refusal_the_board_does_not_show_ends_the_use_without_a_stop(self):
        # DECLARED CONSTRUCTED: the status bar without berserk, for a refusal the
        # board does not name (an anti-magic curse, a NO_MAGIC dungeon).  The
        # game's answer is the recorded screen of the stop, its turn unchanged.
        raw = copy.deepcopy(self.case["board"])
        raw["player"]["status_bar"] = []
        policy = self.primed(raw, [], self.case["skill"])
        key = policy.choose_key(self.board(policy, raw))
        self.assertEqual((key, policy.last_reason), MISSILE)
        game, port, sent = self.post(raw, key, policy.last_reason, self.case["stop_screen"], raw)
        self.assertTrue(sent, port.last_result.reason)
        self.assertEqual(game.accepted, ["m"])
        policy.confirm_key_posted(key)
        answered = port.last_result.board
        self.assertTrue(answered["_magic_eater_command_refused"])
        # The next decision on that board does not repeat the refused key.
        again = policy.choose_key(self.board(policy, answered))
        self.assertEqual((again, policy.last_reason), ("2", "melee"))
