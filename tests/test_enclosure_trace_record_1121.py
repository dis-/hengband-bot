"""The decision record names the routes' vetoes, who left each, and the enclosure ladder's asker.

n1-b life-413 (Angband 12F, 2026-11-21 19:02 and 20:11) dug out of a corridor whose exits were
open; neither stop capture held the vetoes or told the quest search's cut-off opener from the
vetoes' ladder (both post stuck:walled-off-wield-digger), so the asker had to be found by
replaying the run.  flight_recorder.map_memory_summary (every decision row's ``map_memory``) now
carries ``avoid_cells`` and ``enclosure_trace`` (retreat_enclosure ``_traced``).

On the recorded armed board of that stall (tests/fixtures/n1b-413-rearm-digger-loop-1121, turn
674796).  DECLARED CONSTRUCTED: a retreat's vetoes around the corridor turn, claimed through the
production claim with its owner name.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import lzma
import unittest
from pathlib import Path

from hengbot import flight_recorder, retreat_enclosure
from hengbot.model import Position, parse_snapshot
from hengbot.policy import HengbotPolicy
from support.q25_house import RACES

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-413-rearm-digger-loop-1121" / "boards.json.xz"
VETOES = (Position(45, 29), Position(45, 30), Position(45, 31), Position(46, 31), Position(47, 29),
          Position(47, 31))
OWNER = "threat:avoid-engagement"


class EnclosureTraceRecordTest(unittest.TestCase):
    def setUp(self):
        raw = json.loads(lzma.decompress(FIXTURE.read_bytes()))[0]
        self.board = parse_snapshot(raw, RACES)
        self.policy = HengbotPolicy()
        self.policy._monrace_knowledge = RACES
        self.policy._build_grid_index(self.board)

    def test_no_veto_is_recorded_as_none(self):
        summary = flight_recorder.map_memory_summary(self.policy)
        self.assertEqual(summary["avoid_cells"]["owned"], 0)
        self.assertEqual(summary["avoid_cells"]["owned_cells"], [])
        self.assertIsNone(summary["enclosure_trace"])

    def test_the_vetoes_their_owner_and_the_ladders_asker_are_recorded(self):
        policy = self.policy
        policy._claim_engagement_avoid_cells(VETOES, snapshot=self.board, owner=OWNER)
        key = retreat_enclosure.walled_off_key(policy, self.board)
        self.assertIsNotNone(key)
        summary = flight_recorder.map_memory_summary(policy)
        cells = summary["avoid_cells"]["owned_cells"]
        self.assertEqual(sorted((y, x) for y, x, _owners in cells),
                         sorted((cell.y, cell.x) for cell in VETOES))
        self.assertTrue(all(owners == [OWNER] for _y, _x, owners in cells), cells)
        trace = summary["enclosure_trace"]
        self.assertEqual((trace["asker"], trace["turn"], trace["reason"]),
                         ("walled-off", self.board.turn, policy.last_reason))
        self.assertGreater(trace["ground"], 0)
        json.dumps(summary)   # the decision row is JSON

    def test_the_cut_off_openers_asker_is_its_own(self):
        policy = self.policy
        here = self.board.player.position
        key = retreat_enclosure.open_toward_key(
            policy, self.board, [here], [Position(46, 27), Position(46, 26)])
        self.assertIsNotNone(key)
        self.assertEqual(retreat_enclosure.trace(policy)["asker"], "cut-off")


if __name__ == "__main__":
    unittest.main()
