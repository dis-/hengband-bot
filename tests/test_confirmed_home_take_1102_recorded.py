"""n1-b life-295 19:49:09 town:blocked:survival:remove_curse_ready.

A heavily cursed ring of Ice was worn (decision 27215 marked it HEAVY_CURSE
after a normal Remove Curse failed); Home holds a *Remove Curse* scroll
(Home list of turn 1231601).  The supply-stockout mining set was open and
its kit came from Home: 27247 queued 財宝感知の巻物 with the shovel behind it,
27248 took the scroll (its take confirmed, the Home list no longer holds it)
and left.  Outside Home the confirmed take stayed the pending withdrawal, so
the Home leg's terminal targeted it and was refused as reservation-unavailable
(27251), the shovel was never taken, the Home *Remove Curse* bind
(_bind_home_star_remove_curse_withdrawal) waits on any pending withdrawal,
and the town end stopped.

The confirmed take whose item has left the current Home list now ends its
pending withdrawal on the outside board, and the queued shovel leads the
Home leg.
DECLARED RECONSTRUCTED: the pending item with its confirmed take and the
batch (named by 27251's refused home-withdraw terminal) and the open mining
set (27244 fundraise:supply-stockout-mining); the restarted policy primes on
the recorded board.
Fixture: tests/extract_confirmed_home_take_1102_fixture.py.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.model import TVAL_SCROLL, _parse_items, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.town_terminal import gather_home_withdraw, verdict_home_withdraw
from tests import test_input_executor as executor_pins
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURE = Path(__file__).with_name("fixtures") / "confirmed-home-take-1102.json.gz"
TREASURE = ("財宝感知の巻物", 70, 26)
SHOVEL = ("シャベル (1d2) (+0,+0) (+1) {+掘}", 20, 1)
SV_SCROLL_STAR_REMOVE_CURSE = 15


class ConfirmedHomeTakeTest(executor_pins.ProductionHarness):

    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)

    def test_confirmed_take_absent_from_home_is_released(self):
        decisions = {d["decision_sequence"]: d for d in self.case["decisions"]}
        self.assertIn("財宝感知の巻物(f)を取った。", decisions[27249]["messages"])
        self.assertEqual(decisions[27251]["reason"], "town:blocked:survival:remove_curse_ready")
        self.assertEqual(decisions[27251]["departure_failed"],
                         ["remove_curse_ready", "home_pending_item_clear",
                          "home_pending_batch_clear"])
        refused = {a["rung"]: (a["terminal"], a["codes"])
                   for a in decisions[27251]["terminal_admission"]}
        self.assertEqual(refused["_shopping_approach_key#2"],
                         (["home-withdraw", [list(TREASURE), [list(SHOVEL)]]],
                          ["reservation-unavailable"]))

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
        stored = {policy._item_signature(i) for i in home}
        self.assertNotIn(TREASURE, stored)
        self.assertIn(SHOVEL, stored)
        self.assertTrue(any(i.tval == TVAL_SCROLL and i.sval == SV_SCROLL_STAR_REMOVE_CURSE
                            for i in home))
        self.assertIn(TREASURE, {policy._item_signature(i) for i in board.inventory})
        self.assertEqual(policy._required_remove_curse_kind(board), "star-remove-curse")
        self.assertFalse(verdict_home_withdraw(
            gather_home_withdraw(policy, board, target=TREASURE)).admitted)
        # DECLARED RECONSTRUCTED: the confirmed take still pending, the shovel
        # queued behind it, and the open stockout mining set.
        policy._home_pending_item = TREASURE
        policy._home_pending_take_confirmed = TREASURE
        policy._home_pending_batch = [SHOVEL]
        policy._open_one_mining_run()

        board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), monrace))
        key = policy.choose_key(board)
        self.assertIsNone(policy._home_pending_item)
        self.assertEqual(policy._home_pending_batch, [SHOVEL])
        self.assertFalse(policy.last_reason.startswith("town:blocked"), policy.last_reason)
        self.assertEqual(policy.last_reason, "shop:approach")

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
            decision={"sequence": 27251, "reason": policy.last_reason},
            snapshot=board, posting_contract=PostingContract(),
        )
        self.assertEqual(game.accepted, list(key))
        self.assertTrue(sent, port.last_result.stop_line)


if __name__ == "__main__":
    import unittest
    unittest.main()
