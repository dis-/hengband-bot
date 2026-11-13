"""n1-b life-394: the me-staff expedition target drift (2026-11-14).

life-394 (Magic-Eater Lv 7, Outpost, 01:51, quest:blocked:me-staff
fundraise-target-drift:rumor-travel-recharge:3672): back from a met run with 3,508 gold, the
rumor phase opened a run for 3,672.  While the run prepared, ``_expedition_run_unneeded``
priced the trip at 3,429 (the supply ledger leaves out the recall scroll read at departure
while a fundraising run is open) and ended the run as met; the next board priced it at 3,672
again and opened another.  Four boards counted the six met runs of the drift stop.

The fix: ``me_staff_sequence.supply_cost`` reads the ledger of the expedition's own departure,
outside any fundraising mode, so the trip is priced alike in and out of the run.

Recorded (tests/fixtures/n1b-393-394-1114/me-staff-394, see
tests/extract_n1b_393_394_1114_fixtures.py): the town-arrival checkpoint and its journal of
five rows, decided by the public ``choose_key``; the stop board's key is posted through the
production decision send and executor (``_ExecutorInputPort``).
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import json
from pathlib import Path
import unittest

from hengbot import me_staff_sequence
from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from replay_town_arrival import journal
from test_me_stops_1103_recorded import Visit
from tests.support.recorded import FaithfulHookGame, ProductionHarness, command_screen

FIXTURES = Path(__file__).with_name("fixtures") / "n1b-393-394-1114"


class MeStaffDrift394RecordedTest(ProductionHarness):
    def visit(self):
        visit = Visit((FIXTURES / "me-staff-394").resolve())
        visit.policy._home_disposal.history_path = visit.scratch / "home-history.jsonc"
        self.addCleanup(visit.close)
        return visit

    def post(self, visit, board, key):
        """``key`` on the visit's last board through the production decision send
        (cli._send_new_decision_key) and the executor; the game's accepted keys."""
        policy = visit.policy
        entry = list(journal(Path(visit._directory.name) / "town-arrival"))[-1]
        raw = json.loads(entry["line"] if entry["line"] is not None else entry["inputs"][-1])
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        game.screens = [command_screen(raw["turn"] + 10)]
        game.states = [dict(copy.deepcopy(raw), turn=raw["turn"] + 10, messages=[])]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=board, posting_contract=PostingContract())
        self.assertTrue(sent, port.last_result.stop_line)
        self.assertEqual(port.last_result.outcome, "completed", port.last_result.reason)
        return game.accepted

    def test_the_record_ends_three_waits_later_as_target_drift(self):
        visit = self.visit()
        record = me_staff_sequence.state(visit.policy)
        self.assertEqual((record.reached_runs, record.fundraise_target), (1, 3507))
        rows = [recorded for recorded, _supply in visit.rows]
        self.assertEqual([row["key"] for row in rows[1:4]], ["5", "5", "5"])
        self.assertTrue(all(row["reason"].endswith(":3672") for row in rows[:4]))
        self.assertEqual((rows[4]["key"], rows[4]["reason"]), ("", me_staff_sequence.STOP_REASON))

    def test_the_run_opened_for_the_trip_is_carried_out(self):
        visit = self.visit()
        policy = visit.policy
        reasons = []
        for recorded, supply in visit.rows:
            board = supply()
            key = policy.choose_key(board)
            decided = (board, key)
            reasons.append(policy.last_reason)
            visit.post(key)
        record = me_staff_sequence.state(policy)
        self.assertIsNone(record.failure, reasons)
        self.assertNotIn(me_staff_sequence.STOP_REASON, reasons)
        self.assertEqual((record.reached_runs, record.fundraise_target), (2, 3672))
        self.assertEqual(policy._fundraising_mode, "prepare")
        # The trip is priced alike in and out of the run (the expedition's own departure).
        board, key = decided
        priced = me_staff_sequence.supply_cost(policy, board)
        with policy._outside_fundraising():
            self.assertEqual(priced, me_staff_sequence.supply_cost(policy, board))
        # The record's stop board: the run's errands go on, and the step reaches the game.
        self.assertEqual((policy.last_reason, key), ("shop:approach", "4"))
        self.assertEqual(self.post(visit, board, key), ["4"])


if __name__ == "__main__":
    unittest.main()
