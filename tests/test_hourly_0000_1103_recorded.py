"""The 2026-11-03 viewing-bot stops of hourly-0000-1103.

Each class pins one root on its recorded board; facts the capture keeps
outside the board are marked DECLARED RECONSTRUCTED.
Fixture: tests/extract_hourly_0000_1103_fixtures.py.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.equipment_optimizer import equipment_identity, equipment_move_identity
from hengbot.equipment_transaction_planner import EquipmentTransaction, EquipmentTransactionPlan
from hengbot.equipment_transaction_session import EquipmentTransactionSession
from tests import test_input_executor as executor_pins
from test_hourly_0700_1102_recorded import RecordedTownPolicy


FIXTURE = Path(__file__).with_name("fixtures") / "hourly-0000-1103.json.gz"
TVAL_AMULET = 40


def _cases():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return json.load(stream)


class OutsideEquipBeforeHomeReentryTest(RecordedTownPolicy, executor_pins.ProductionHarness):
    """n1-c life-112 00:25:46 town:blocked:owner-retired-burst.

    In Morivant the equipment session's one action was to wear the carried
    耐電のアミュレット (pack n) on the empty neck slot, an equip outside Home.
    The town plan's first stop was Home, and the Home route (owned by the
    session, purpose equipment-work) went in (9158); inside, the session
    left with equipment-transaction:leave-home-for-equip; outside the
    identification owner identified one pack weapon, then the Home route
    waited on the entrance to go in again (9161 ``5``) before the equip.
    Three leave/identify/enter rounds later the store router had retired
    three times and the bot stopped with the amulet still in the pack.
    """

    @classmethod
    def setUpClass(cls):
        cls.case = _cases()["equip"]

    def policy(self, name):
        case = self.case
        raw = case["boards"][name]
        policy = self.primed(raw, case["home"]["knowledge"]["items"], case["skill"])
        board = self.board(policy, raw)
        (amulet,) = [item for item in board.inventory if item.tval == TVAL_AMULET]
        recorded = case["decisions"][0]
        # DECLARED RECONSTRUCTED: captures omit the session object; every
        # recorded row of the visit shows this one unposted action
        # (transaction_next) of the carried amulet, and the Home candidate
        # latch (home_candidate_waiting) that put Home first in the plan.
        action = recorded["transaction_next"]
        policy._equipment_transaction_session = EquipmentTransactionSession(
            EquipmentTransactionPlan((EquipmentTransaction(
                **action, item_identity=equipment_identity(amulet),
                move_identity=equipment_move_identity(amulet)),), (), len(raw["inventory"])))
        policy._home_candidate_waiting = True
        return policy, board, raw

    def test_recorded_rounds(self):
        rows = {row["decision_sequence"]: row for row in self.case["decisions"]}
        self.assertEqual((rows[9158]["reason"], rows[9158]["key"]), ("shop:travel", "\x1b`n(."))
        self.assertEqual((rows[9161]["reason"], rows[9161]["key"]), ("shop:travel:await-entry", "5"))
        self.assertEqual(rows[9181]["reason"], "town:blocked:owner-retired-burst")
        for row in rows.values():
            self.assertEqual(row["transaction_next"],
                             {"phase": "equip", "kind": "equip",
                              "item_id": "pack:8486b7fecf6c8c06:0", "target_slot": "neck"})
            self.assertEqual(row["context"], "outside_home")
        self.assertEqual([rows[s]["reason"] for s in (9165, 9171, 9177)],
                         ["equipment-transaction:leave-home-for-equip"] * 3)

    def test_the_outside_equip_is_worn_before_the_home_route(self):
        for name in ("travel", "entrance"):
            with self.subTest(board=name):
                policy, board, raw = self.policy(name)
                key = policy.choose_key(board)
                # Recorded: Home travel (9158) / await-entry (9161).
                self.assertEqual((key, policy.last_reason), ("wn", "equipment-transaction:equip"))
                self.post(policy, board, raw, key)

    def post(self, policy, board, raw, key):
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_pins.command_screen(raw["turn"])
        # DECLARED CONSTRUCTED: the game's equip prompt (cmd-item/
        # cmd-equipment.cpp) and the following board with the amulet worn.
        worn = copy.deepcopy(raw)
        worn["turn"] += 10
        amulet = next(item for item in worn["inventory"] if item["slot"] == "n")
        worn["inventory"].remove(amulet)
        worn["equipment"].append(dict(amulet, slot="neck"))
        game.screens = [executor_pins.prompt_screen("(持ち物: a-r, ESC) どれを装備しますか? "),
                        executor_pins.command_screen(worn["turn"])]
        game.states = [copy.deepcopy(worn) for _ in game.screens]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=board, posting_contract=PostingContract())
        self.assertTrue(sent, port.last_result.stop_line)
        self.assertEqual("".join(game.accepted), key)


if __name__ == "__main__":
    unittest.main()
