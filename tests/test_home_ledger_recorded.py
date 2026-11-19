"""The Home ledger, Home root fix stage 1 (owner 2026-11-19 「自宅の満杯問題で問題を起こしすぎなので
根本解決すること」, PROPOSAL C:\\hengband-backups\\pdca\\home-full-root-1119 3-1 and 3-6).

Record only: on the first board of a town visit with a current Home census the ledger records
each stack's fate (item_fate.fate) and how far the Home stands over the cap of 200 (owner
「200件（空き40）」), and the decision log carries it on that one decision (home_ledger.report).
The decisions are unchanged: the replayed rows equal the recorded ones.

Recorded: n1-a life-531's town-arrival checkpoint of 2026-11-19 03:27:20 and its first journal
rows (tests/extract_n1a_531_overweight_1119_fixture.py): a full Home (240/240) holding the six
Rods of Trap Location no rule uses, the top ten of each slot and the unidentified loot.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import home_ledger, item_fate
from support.town_arrival_fixture import load
from test_n1a_531_overweight_1119_recorded import post

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-531-overweight-1119"
ROWS = 3
TVAL_ROD = 66


class HomeLedgerRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, cls.journal, steps = load(FIXTURE, Path(cls.scratch.name))
        cls.policy = policy
        cls.rows = []
        for row, (recorded, supply) in enumerate(steps[:ROWS]):
            board = supply()
            before = copy.copy(policy._store_visit)
            key = policy.choose_key(board)
            cls.rows.append(((key, policy.last_reason), (recorded["key"], recorded["reason"]),
                             home_ledger.report(policy), policy._decision_sequence))
            post(policy, board, recorded["key"], before)
            cls.board = board

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def test_the_decisions_are_unchanged(self):
        for row, (decided, recorded, _, _) in enumerate(self.rows):
            self.assertEqual(decided, recorded, row)

    def test_one_record_per_visit_on_its_decision(self):
        reports = [report for _, _, report, _ in self.rows]
        self.assertIsNotNone(reports[0])
        self.assertEqual(reports[1:], [None] * (ROWS - 1))
        state = self.policy._home_ledger
        self.assertEqual(state["epoch"], self.policy._town_visit_epoch)
        self.assertEqual(state["note"][0], self.rows[0][3])

    def test_the_record_counts_the_home_against_its_cap(self):
        summary = self.rows[0][2]
        self.assertEqual(summary["home"], {"count": 240, "cap": 200})
        self.assertEqual(sum(summary["fates"].values()), 240)
        self.assertTrue(summary["fits"])
        self.assertLessEqual(summary["kept"], 200)
        # The first visit sheds the 40 over the cap, none of them kept stock.
        self.assertEqual(summary["shed"]["count"], 40)
        self.assertEqual(summary["shed"]["short"], 0)
        self.assertEqual(set(summary["shed"]["fates"]) - {"destroy", "sell", "room-sale"}, set())

    def test_each_stack_has_one_fate(self):
        policy, board = self.policy, self.board
        fates = {}
        for item in policy._home_knowledge_items:
            fates.setdefault(item_fate.fate(policy, board, item, item_fate.SHELF), []).append(item)
        # The six Rods of Trap Location no rule uses are sold (owner 2026-11-19).
        self.assertIn((TVAL_ROD, 0, 6), [(item.tval, item.sval, item.count)
                                         for item in fates[item_fate.SELL]])
        # Every top-ten piece and every artifact stays.
        for item in policy._home_knowledge_items:
            if item.is_artifact:
                self.assertEqual(item_fate.fate(policy, board, item, item_fate.SHELF),
                                 item_fate.HOME)
        for item in fates.get(item_fate.ROOM_SALE, []):
            self.assertEqual(item_fate.gear_tier(policy, board, item), item_fate.ROOM)
        # Worn gear is carried; an unidentified Home stack waits for a means.
        self.assertEqual({item_fate.fate(policy, board, item, item_fate.WORN)
                          for item in board.equipment}, {item_fate.CARRY})
        unknown = replace(policy._home_knowledge_items[0], known=False)
        self.assertEqual(item_fate.fate(policy, board, unknown, item_fate.SHELF),
                         item_fate.IDENTIFY)


if __name__ == "__main__":
    unittest.main()
