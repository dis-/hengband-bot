"""n1-c life-217, Quest 33 段2 (2026-11-19 23:13-23:14): the Gachapin the lure waited for went back and forth.

After the restart record was seeded the lure began at once and held the start [20,48] its 200 turns
(tests/fixtures/n1c-217-q33-gachapin-wait-1119.json.gz, extracted by
tests/extract_n1c_217_q33_gachapin_wait_1119_fixture.py from C:/hengband-backups/pdca/captures/
n1c-217-q33-lure2-1119); with no other start the sweep stopped by name
(quest:blocked:sweep-nothing-comes).  On every held board the Gachapin within its vision of 10 stood
at [23,57] or [23,56] in turn, the one at [24,57] (11 away, not acting) and the one at [21,59] still.

The game (monster-floor/monster-sweep-grid.cpp ``NoiseTrackingMoveGridDecider``) heads a monster not
for the flow's next cell but for the point 16 grids past the player in that cell's direction: from
[23,57] the flow's least neighbour is [24,57] (south), the point is [36,48], and of the five directions
toward it (get_moves_val) south-west is wall, south is the Gachapin that does not act, west is free;
from [23,56] the least neighbour is [24,57] again (south-east), the point [36,64], and east is free.
The old reading (a way out of the room and the flow within 32) said it came; quest_wait_placement now
follows its steps as the game makes them.  The same reading tells the earlier boards' non-comers: the
Dagon at [23,44] from [15,38] (n1-c 19:25-20:00), the Queens from [14,47] (20:31-20:59), and the
ボーシン, level 10, who run from the Lv44 player (mon_will_run, the index's 8 and the HP counted).

DECLARED CONSTRUCTED: the policy is n1-c life-217's town arrival of the same day
(tests/fixtures/quest32-one-turn-kill-1119/n1c-217, tests/test_quest33_alignment_split ``recorded``);
the kill lines of the three Its, Dagons and Bokrugs are set on the navigator (the seeded restart record
held them); the earlier boards are the fixtures of those runs.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import gzip
import json
import unittest
from pathlib import Path

from hengbot import quest_lure_approach, quest_plan_base, quest_room_sweep, quest_wait_placement
from hengbot.model import parse_snapshot
from hengbot.quest_plan_base import _navigator
from tests.test_quest33_alignment_split import BOKRUG, DAGON, GACHAPIN, IT, QUEEN, QUEST, quest_dir, recorded

FIXTURES = Path(__file__).with_name("fixtures")
BOSHIN = 177


class N1c217Q33GachapinWaitTest(unittest.TestCase):
    def setUp(self):
        if quest_dir() is None:
            self.skipTest("the Hengband quest data is not available")
        self.scratch, self.policy, _town = recorded("n1c-217")
        self.addCleanup(self.scratch.cleanup)
        self.plan = self.policy.approved_quest_strategy(QUEST).engagement_plan["room_sweep"]

    def board(self, name, kills):
        with gzip.open(FIXTURES / name, "rt", encoding="utf-8") as stream:
            case = json.load(stream)
        snapshot = parse_snapshot(case["board"], self.policy._monrace_knowledge)
        navigator = _navigator(self.policy, snapshot, QUEST)
        navigator.split_kills = dict(kills)
        read = quest_wait_placement.reader(self.policy, snapshot, navigator, self.plan)
        return case, snapshot, navigator, read

    def row(self, read, cell):
        return next(row for row in read.rows if row.cell == cell)

    def test_the_recorded_gachapin_went_back_and_forth(self):
        case, _snapshot, _navigator_, _read = self.board("n1c-217-q33-gachapin-wait-1119.json.gz",
                                                         {IT: 3, DAGON: 3, BOKRUG: 3})
        self.assertEqual(case["runs"][-1]["reason"], quest_room_sweep.NOTHING_COMES_REASON)
        self.assertGreaterEqual(len(case["held"]), 90)
        self.assertEqual({tuple(map(tuple, cells)) for _turn, cells in case["held"]},
                         {((21, 59), (23, 56), (24, 57)), ((21, 59), (23, 57), (24, 57))})

    def test_the_reader_follows_its_steps_and_finds_it_does_not_come(self):
        _case, _snapshot, _navigator_, read = self.board("n1c-217-q33-gachapin-wait-1119.json.gz",
                                                         {IT: 3, DAGON: 3, BOKRUG: 3})
        mover = self.row(read, (23, 57))
        self.assertTrue(read.acts(mover, (20, 48)))
        self.assertFalse(read.comes(mover, (20, 48)))
        headings = []
        original = read._heading

        def heading(row, cell, spot, gauge, flags, doors):
            target = original(row, cell, spot, gauge, flags, doors)
            headings.append((cell, target))
            return target

        read._heading = heading
        self.assertFalse(read.walks(mover, (20, 48), read._blocked(mover, (20, 48))))
        self.assertEqual(headings, [((23, 57), (36, 48)), ((23, 56), (36, 64))])

    def test_the_lure_now_starts_where_a_gachapin_walks_to_the_player(self):
        _case, snapshot, navigator, read = self.board("n1c-217-q33-gachapin-wait-1119.json.gz",
                                                      {IT: 3, DAGON: 3, BOKRUG: 3})
        paths = []
        original = quest_plan_base._path_step

        def recording(policy, board, path, reason):
            paths.append([(cell.y, cell.x) for cell in path])
            return original(policy, board, path, reason)

        quest_plan_base._path_step = recording
        self.addCleanup(setattr, quest_plan_base, "_path_step", original)
        self.assertIsNotNone(quest_room_sweep.walk_key(self.policy, snapshot))
        self.assertEqual(self.policy.last_reason, quest_lure_approach.LURE_WALK_REASON)
        start = paths[-1][-1]
        self.assertNotEqual(start, (20, 48))
        gachapins = [row for row in read.rows if row.race == GACHAPIN]
        self.assertTrue(any(read.comes(row, start) for row in gachapins))
        queens = quest_lure_approach._rows(self.policy, snapshot, navigator, self.plan, read, [QUEEN])
        self.assertFalse(any(quest_lure_approach._line_of_fire(read, row, start) for row in queens))

    def test_the_earlier_non_comers(self):
        _case, _snapshot, _navigator_, read = self.board("n1c-217-q33-stage-loop-1119.json.gz", {IT: 3})
        self.assertFalse(read.comes(self.row(read, (23, 44)), (15, 38)))
        for cell in [(19, 53), (21, 54)]:
            boshin = self.row(read, cell)
            self.assertEqual(boshin.race, BOSHIN)
            self.assertTrue(read._runs(boshin, (15, 38)))
        # The Dagons came to the top of the column (killed 20:25-20:26 after the stand [18,39]).
        self.assertTrue(all(read.comes(self.row(read, cell), (18, 39)) for cell in [(23, 44), (25, 44), (25, 45)]))
        _case, _snapshot, _navigator_, read = self.board("n1c-217-q33-queen-wait-1119.json.gz",
                                                         {IT: 3, DAGON: 3, BOKRUG: 3})
        queens = [row for row in read.rows if row.race == QUEEN]
        self.assertEqual(len(queens), 3)
        self.assertTrue(all(read.acts(row, (14, 47)) and not read.comes(row, (14, 47)) for row in queens))


if __name__ == "__main__":
    unittest.main()
