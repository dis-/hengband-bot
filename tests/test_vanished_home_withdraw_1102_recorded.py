"""n1-a life-464 07:12:40 town:blocked:survival:cure_critical_ready.

Owner rule (2026-11-02): 「満たせなければ採掘を1サイクル行い再度トライ。
条件未達の出発は拒否する。」  The town end opened the mining cycle (2301),
but on the next board (2302) the cycle could not leave: its departure needs
Treasure Detection, the four stored in Home were reachable only through the
Home leg, and that leg's only terminal was the legacy withdrawal of
ドラゴン・グローブ [4,+8] {r呪}, which the full-Home discard had taken (2293)
and destroyed (2295).  The current Home list (turn 3311414) lacks it, so the
Home withdrawal verdict refused it (reservation-unavailable) on every board.

The withdrawal is now retired on the board itself: an item neither in the
current Home list nor carried ends its pending withdrawal and its filed
Home visit request.
DECLARED RECONSTRUCTED: the pending withdrawal and its filed request (named
by decision 2302's refused home-withdraw terminal) and the open mining cycle
(decision 2301); the restarted policy primes on the recorded board.
Fixture: tests/extract_vanished_home_withdraw_1102_fixture.py.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.home_visit import HomeVisitKind
from hengbot.model import TVAL_SCROLL, _parse_items, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.town_terminal import gather_home_withdraw, verdict_home_withdraw
from tests.support import recorded as executor_pins
from tests.support.recorded import EDIT, _policy


FIXTURE = Path(__file__).with_name("fixtures") / "vanished-home-withdraw-1102.json.gz"
GLOVES = ("ドラゴン・グローブ [4,+8] {r呪}", 31, 3)
SV_SCROLL_TREASURE_DETECTION = 26


class VanishedHomeWithdrawTest(executor_pins.ProductionHarness):

    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)

    def test_withdrawal_of_a_destroyed_item_is_retired(self):
        decisions = {d["decision_sequence"]: d for d in self.case["decisions"]}
        self.assertIn("ドラゴン・グローブ [4,+8] {r呪}を壊した。", decisions[2295]["messages"])
        self.assertEqual(decisions[2301]["reason"], "town:end-mining-cycle")
        self.assertEqual(decisions[2302]["reason"], "town:blocked:survival:cure_critical_ready")
        refused = {a["rung"]: (a["terminal"], a["codes"])
                   for a in decisions[2302]["terminal_admission"]}
        self.assertEqual(refused["_shopping_approach_key#2"],
                         (["home-withdraw", [list(GLOVES), []]], ["reservation-unavailable"]))

        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        policy = _policy(Path(directory.name), monrace)
        raw = self.case["board"]
        board = parse_snapshot(copy.deepcopy(raw), monrace)
        policy.prime(board)
        policy.consume_skill_knowledge(
            {**self.case["skill"], "player": {"level": board.player.level}})
        home = tuple(_parse_items(self.case["home"]["knowledge"]["items"], protocol=3))
        policy.consume_home_knowledge(home)
        self.assertNotIn(GLOVES, {policy._item_signature(i) for i in home})
        self.assertEqual(sum(i.count for i in home if i.tval == TVAL_SCROLL
                             and i.sval == SV_SCROLL_TREASURE_DETECTION), 4)
        self.assertNotIn(GLOVES, {policy._item_signature(i)
                                  for i in (*board.inventory, *board.equipment)})
        self.assertFalse(verdict_home_withdraw(
            gather_home_withdraw(policy, board, target=GLOVES)).admitted)
        # DECLARED RECONSTRUCTED: the live pending withdrawal, filed, and the
        # mining cycle the town end opened at 2301.
        policy._home_pending_item = GLOVES
        self.assertTrue(policy._ensure_home_visit_request(board))
        self.assertEqual((policy._home_visit.request.kind, policy._home_visit.request.item_identity),
                         (HomeVisitKind.WITHDRAW, GLOVES))
        policy._open_one_mining_run()

        board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), monrace))
        key = policy.choose_key(board)
        self.assertIsNone(policy._home_pending_item)
        request = policy._home_visit.request
        self.assertFalse(request is not None and request.item_identity == GLOVES)
        self.assertEqual(policy._pending_home_visit_report,
                         "home-visit:legacy-withdrawal:reservation-unavailable")
        self.assertFalse(policy.last_reason.startswith("town:blocked"))

        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = [executor_pins.command_screen(raw["turn"] + 10)]
        game.states = [copy.deepcopy(raw)]
        # DECLARED CONSTRUCTED: the step spent one player turn.
        game.states[-1]["turn"] = raw["turn"] + 10
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": 2302, "reason": policy.last_reason},
            snapshot=board, posting_contract=PostingContract(),
        )
        self.assertEqual(game.accepted, list(key))
        self.assertTrue(sent, port.last_result.stop_line)


if __name__ == "__main__":
    import unittest
    unittest.main()
