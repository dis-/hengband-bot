"""n1-a life-482 (2026-11-05 02:12): the Home reserve took what the weight relief shed.

A Lv31 warrior stopped on town:blocked:owner-retired-burst.  The Home reserve took
an Identify staff (20 charges wanted, 7 reachable); the weight relief put a staff
back, because a stack bought this visit was reserved for the bought count only and
the rest counted as spare.  The ammunition, which fits the weight limit by the
owner's 2026-10-01 rule, had already filled the pack to exactly 1700 of 1700.

Now a required supply reserved only as bought this visit stays out of the relief,
as one with no reservation always did; the bolts give way by the least count.

Recorded: the arrival checkpoint and rows 0-65 of its journal replay unchanged;
row 66 is the first changed board.  DECLARED CONSTRUCTED: the rows after it
(tests/extract_town_staff_weight_fixture.py), since no recorded board exists on
the fixed path.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import gzip
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.town_arrival_checkpoint import JOURNAL_FILE, POLICY_FILE
from replay_town_arrival import adopt_calibration, decisions, journal, restore
from tests.support import recorded as executor_pins
from town_work_corpus import replay_window


FIXTURE = Path(__file__).with_name("fixtures") / "town-staff-weight-1105"
CHANGED_ROW = 66
RECORDED_SHED = "dm71\rdjdh2\rde2\r\x1b"  # 2 of the 3 two-charge staves back to Home
FIXED_SHED = "dm85\rdjde2\r\x1b"  # bolts, the third digger, 2 spare Recall scrolls
OVERWEIGHT_SHED = "home:weight-overload-deposit"


def xz_lines(name):
    return lzma.decompress((FIXTURE / name).read_bytes())


def home_page_screen(store):
    """The live Home page: its 52 rows need a taller terminal than the harness's."""
    screen = executor_pins.store_screen()
    menu = screen["lines"][20:22]
    screen["lines"] = screen["lines"][:6] + [""] * 56
    screen["height"] = len(screen["lines"])
    screen["lines"][5] = " " * 20 + f"(Page {store['page_top'] // store['page_size'] + 1})"
    for index, item in enumerate(store["items"]):
        screen["lines"][6 + index] = f"{item['letter']}) {item['name']}"
    screen["lines"][58:60] = menu
    screen["cursor"] = {"visible": True, "y": 58, "x": 0}
    return screen


class TownStaffWeightRecordedTest(executor_pins.ProductionHarness):
    def setUp(self):
        super().setUp()
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        visit = Path(scratch.name) / "town-arrival"
        visit.mkdir()
        (visit / POLICY_FILE).write_bytes(xz_lines("policy.pkl.xz"))
        (visit / JOURNAL_FILE).write_bytes(gzip.compress(
            xz_lines("journal.jsonl.xz") + xz_lines("continuation.jsonl.xz")))
        runtime = Path(scratch.name) / "runtime"
        runtime.mkdir()
        self.policy = restore(visit, runtime)
        # The tests share the isolated runtime directory; each has its own history.
        Path(self.policy._home_disposal.history_path).unlink(missing_ok=True)
        adopt_calibration(self.policy, FIXTURE / "character-calibration.json", runtime)
        Path(self.policy._character_dump_path).write_bytes(
            (FIXTURE / "character-dump.txt").read_bytes())
        self.rows = journal(visit)
        self.steps = list(decisions(self.policy, visit, runtime))

    def decide_changed_board(self):
        result = replay_window("before-the-shed", self.policy, iter(self.steps[:CHANGED_ROW]))
        self.assertIsNone(result.first_divergence)
        self.assertEqual(result.matched_rows, CHANGED_ROW)
        self.assertEqual(self.rows[CHANGED_ROW]["key"], RECORDED_SHED)
        board = self.steps[CHANGED_ROW][1]()
        return board, self.policy.choose_key(board)

    def test_overload_sheds_bolts_and_keeps_the_staves(self):
        board, key = self.decide_changed_board()
        self.assertEqual((key, self.policy.last_reason), (FIXED_SHED, OVERWEIGHT_SHED))
        self.assertEqual([(item.count, item.charges) for item in board.inventory
                          if item.tval == 55 and item.sval == 5], [(3, 2), (1, 1)])
        self.policy.confirm_key_posted(key)

        raw_board = json.loads(self.rows[CHANGED_ROW]["line"])
        game = executor_pins.FaithfulHookGame()
        game.state = raw_board
        game.jsonl = [raw_board]
        # DECLARED CONSTRUCTED: the shelf screen and the next board after the operation.
        game.screen = home_page_screen(raw_board["store"])
        game.screens = [executor_pins.command_screen(raw_board["turn"] + 10)]
        game.states = [dict(raw_board, turn=raw_board["turn"] + 10)]
        _game, _client, executor = self.make(game)
        result = executor.observe_boundary(deadline=9999999999)
        self.assertEqual(result.outcome, "ready", result)
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=True,
            decision={"sequence": self.policy._decision_sequence, "reason": self.policy.last_reason},
            snapshot=board, posting_contract=PostingContract())
        self.assertTrue(sent, port.last_result.stop_line)
        self.assertEqual(game.accepted, [key])

    def test_constructed_rest_of_the_visit_leaves_for_the_dungeon(self):
        _board, key = self.decide_changed_board()
        self.assertEqual(key, FIXED_SHED)
        self.policy.confirm_key_posted(key)
        rest = self.steps[CHANGED_ROW + 1:]
        result = replay_window("to-the-entrance", self.policy, iter(rest))
        self.assertIsNone(result.first_divergence)
        self.assertEqual(result.matched_rows, len(rest))
        reasons = [row["reason"] for row in self.rows[CHANGED_ROW + 1:]]
        self.assertEqual(reasons[-1], "town:travel-entrance")
        self.assertNotIn("home:queue-withdraw-identify-staff-reserve", reasons)
        self.assertIn("home:identify-staff-reserve-unavailable", reasons)

        last = json.loads(self.rows[-1]["inputs"][-1])
        carried = {(item["tval"], item["sval"]): item["count"]
                   for item in last["inventory"] if "sval" in item}
        # Speed, Cure Critical, Healing, Teleport, Recall: every survival target whole.
        self.assertEqual([carried[key] for key in
                          ((75, 29), (75, 36), (75, 37), (70, 9), (70, 11))],
                         [10, 10, 10, 15, 10])
        self.assertEqual(sum(item["count"] * item["charges"] for item in last["inventory"]
                             if item["tval"] == 55 and item["sval"] == 5), 7)
        self.assertLessEqual(sum(item["weight"] * item["count"] for item in
                                 (*last["inventory"], *last["equipment"])), 1700)


if __name__ == "__main__":
    unittest.main()
