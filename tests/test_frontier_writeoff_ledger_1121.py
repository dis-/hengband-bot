"""The floor's ledger keeps why each frontier was written off, across a restart.

n1-b life-413 (Angband 12F, 2026-11-21 19:02 and 20:11): the explore had written off the corridor
running east from (46,30) (it was floor: walked in the replay of the 20:11 capture's keys), so the
quest search judged the room west of it cut off and dug.  The ledger (jsonlog/exploration-
ledger.json) kept only that the frontier was written off, and it was overwritten on the next
floor, so the cause could not be read.  Each write-off now records its cause and game turn in the
ledger (``writeoffs``, saved with it) and the decision record's map_memory
(``frontier_writeoffs``).

On the recorded armed board of that stall (tests/fixtures/n1b-413-rearm-digger-loop-1121, turn
674796).  DECLARED CONSTRUCTED: the visit counts of the corridor cell east of the player.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import flight_recorder
from hengbot.exploration_ledger import ExplorationLedger
from hengbot.model import Position, parse_snapshot
from hengbot.policy import FRONTIER_EXHAUST_VISITS, HengbotPolicy
from support.q25_house import RACES

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-413-rearm-digger-loop-1121" / "boards.json.xz"
EAST = Position(46, 32)


class FrontierWriteoffLedgerTest(unittest.TestCase):
    def setUp(self):
        raw = json.loads(lzma.decompress(FIXTURE.read_bytes()))[0]
        self.board = parse_snapshot(raw, RACES)
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "exploration-ledger.json"

    def policy(self):
        policy = HengbotPolicy()
        policy._monrace_knowledge = RACES
        ledger = ExplorationLedger(self.path)
        ledger.bind(self.board)
        policy._exploration_ledger = ledger
        policy._probed_frontiers = ledger.probed_frontiers
        policy._build_grid_index(self.board)
        return policy

    def test_the_east_frontier_is_a_frontier(self):
        policy = self.policy()
        self.assertTrue(policy._is_frontier(self.board, self.board.grid_at(EAST)))
        self.assertEqual(policy._exploration_ledger.writeoffs, {})

    def test_a_write_off_keeps_its_cause_across_a_restart(self):
        policy = self.policy()
        policy._visit_counts[EAST] = FRONTIER_EXHAUST_VISITS
        self.assertFalse(policy._is_frontier(self.board, self.board.grid_at(EAST)))
        self.assertEqual(policy._exploration_ledger.writeoffs[(EAST.y, EAST.x)],
                         ("visits-exhausted", self.board.turn))
        summary = flight_recorder.map_memory_summary(policy)["frontier_writeoffs"]
        self.assertEqual(summary["count"], 1)
        self.assertEqual(summary["latest"], [[EAST.y, EAST.x, "visits-exhausted", self.board.turn]])
        policy._exploration_ledger.save(force=True)
        restarted = ExplorationLedger(self.path)
        self.assertTrue(restarted.bind(self.board))
        self.assertIn(EAST, restarted.probed_frontiers)
        self.assertEqual(restarted.writeoffs[(EAST.y, EAST.x)], ("visits-exhausted", self.board.turn))


if __name__ == "__main__":
    unittest.main()
