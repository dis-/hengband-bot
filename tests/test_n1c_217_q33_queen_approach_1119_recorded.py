"""n1-c life-217, Quest 33 段2 (2026-11-19 20:31-20:59): the Gachapins lured out of the Queens' range, then
the Queens closed on from the forest side.

The recorded board (tests/fixtures/n1c-217-q33-queen-wait-1119.json.gz, extracted by
tests/extract_n1c_217_q33_queen_wait_1119_fixture.py, from C:/hengband-backups/pdca/captures/
n1c-217-q33-loop2-1119): the player on [14,47], the three Gachapins sensed at [21,59] [22,57] [20,57],
the Queens never seen (placed at [20,69] [20,72] [22,70]); the plan held [14,47] for the Queens and
walked its stands again until the floor-dwell watcher halted it.

Owner 2026-11-19 (verbatim): 「ガチャピンを先に女王アリの範囲外まで誘導して処理。終わったら森側からなるべく
射線を通さないように女王アリに近づいて処理。壁を溶かすことも考慮に入れること。」  No cell lets a Gachapin
act and no Queen act (the Gachapins' vision 10 lies within the Queens' 30); asked, the owner chose
「射線の外なら許す」: the lure starts on a cell where the Queens act but none has a line of fire; a Gachapin
seen, the player steps back out of their range and kills what follows; a Queen and a Gachapin come
together, he disengages (quest_lure_approach).

DECLARED CONSTRUCTED: the policy is n1-c life-217's town arrival of the same day
(tests/fixtures/quest32-one-turn-kill-1119/n1c-217, tests/test_quest33_alignment_split ``recorded``);
the board is the recorded last one on [14,47], with the player moved on it; the kill lines of the three
Its, Dagons and Bokrugs are set on the navigator (the run killed them, 18:30 and 20:24-20:30); a
Gachapin "seen" is the recorded one moved from the sensed to the seen list and to the cell named; a
Queen on the board is the Gachapin's record with the Queen's race; "the Gachapins dead" sets their
three kill lines and takes them off the board.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot import (
    quest_lure_approach,
    quest_plan_base,
    quest_room_sweep,
    quest_summon_answer,
    quest_wait_placement,
)
from hengbot.model import parse_snapshot
from hengbot.quest_plan_base import _navigator
from tests.test_quest33_alignment_split import BOKRUG, DAGON, GACHAPIN, IT, QUEEN, QUEST, quest_dir, recorded

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-217-q33-queen-wait-1119.json.gz"
QUEEN_STAND = (14, 47)
LURE_START = (22, 47)
FOREST_STAND, QUEEN_WALL = (23, 66), (23, 67)


class N1c217Q33QueenApproachTest(unittest.TestCase):
    def setUp(self):
        if quest_dir() is None:
            self.skipTest("the Hengband quest data is not available")
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            self.case = json.load(stream)
        self.scratch, self.policy, _town = recorded("n1c-217")
        self.addCleanup(self.scratch.cleanup)
        self.plan = self.policy.approved_quest_strategy(QUEST).engagement_plan["room_sweep"]
        self.kills = {IT: 3, DAGON: 3, BOKRUG: 3}
        self.paths = []
        original = quest_plan_base._path_step

        def recording(policy, snapshot, path, reason):
            self.paths.append((reason, [(cell.y, cell.x) for cell in path]))
            return original(policy, snapshot, path, reason)

        quest_plan_base._path_step = recording
        self.addCleanup(setattr, quest_plan_base, "_path_step", original)

    def board(self, cell, *, seen=None, queen=None, gachapins=True):
        raw = copy.deepcopy(self.case["board"])
        raw["player"]["y"], raw["player"]["x"] = cell
        record = next(m for m in raw["detected_monsters"] if m["race_id"] == GACHAPIN)
        if seen is not None:
            raw["detected_monsters"].remove(record)
            raw["visible_monsters"].append({**record, "y": seen[0], "x": seen[1]})
        if queen is not None:
            raw["detected_monsters"].append({**record, "race_id": QUEEN, "index": 90, "y": queen[0], "x": queen[1]})
        if not gachapins:
            raw["detected_monsters"] = [m for m in raw["detected_monsters"] if m["race_id"] != GACHAPIN]
        snapshot = parse_snapshot(raw, self.policy._monrace_knowledge)
        navigator = _navigator(self.policy, snapshot, QUEST)
        navigator.split_kills = dict(self.kills)
        return snapshot, navigator

    def decide(self, snapshot):
        return quest_room_sweep.key(self.policy, snapshot) or quest_room_sweep.walk_key(self.policy, snapshot)

    def rows(self, snapshot, navigator, race):
        read = quest_wait_placement.reader(self.policy, snapshot, navigator, self.plan)
        return read, quest_lure_approach._rows(self.policy, snapshot, navigator, self.plan, read, [race])

    def test_no_cell_lets_a_gachapin_act_and_no_queen(self):
        snapshot, navigator = self.board(QUEEN_STAND)
        read, gachapins = self.rows(snapshot, navigator, GACHAPIN)
        _read, queens = self.rows(snapshot, navigator, QUEEN)
        self.assertEqual(len(gachapins), 3)
        self.assertEqual(sorted(row.cell for row in queens), [(20, 69), (20, 72), (22, 70)])
        cells = [cell for cell, kind in navigator.battlefield.terrain.items() if kind in {"floor", "passage"}]
        self.assertFalse([cell for cell in cells if any(read.acts(row, cell) for row in gachapins)
                          and not any(read.acts(row, cell) for row in queens)])

    def test_the_lure_starts_out_of_every_queen_line(self):
        snapshot, navigator = self.board(QUEEN_STAND)
        self.assertTrue(quest_lure_approach.active(self.policy, snapshot, navigator, self.plan))
        self.assertIsNotNone(self.decide(snapshot))
        self.assertEqual(self.policy.last_reason, quest_lure_approach.LURE_WALK_REASON)
        self.assertEqual(self.paths[-1][1][-1], LURE_START)
        read, gachapins = self.rows(snapshot, navigator, GACHAPIN)
        _read, queens = self.rows(snapshot, navigator, QUEEN)
        self.assertTrue(any(read.comes(row, LURE_START) for row in gachapins))
        self.assertTrue(any(read.acts(row, LURE_START) for row in queens))
        self.assertFalse(any(quest_lure_approach._line_of_fire(read, row, LURE_START) for row in queens))
        # There: held until a Gachapin is seen.
        there, _navigator_ = self.board(LURE_START)
        self.decide(there)
        self.assertEqual(self.policy.last_reason, quest_plan_base.HOLD_REASON)

    def test_a_gachapin_seen_the_player_steps_out_of_the_queens_range(self):
        snapshot, navigator = self.board(LURE_START, seen=(22, 53))
        self.decide(snapshot)
        self.assertEqual(self.policy.last_reason, quest_lure_approach.LURE_BACK_REASON)
        read, queens = self.rows(snapshot, navigator, QUEEN)
        goal = self.paths[-1][1][-1]
        self.assertFalse(any(read.acts(row, goal) for row in queens))
        self.assertTrue(any(read.acts(row, LURE_START) for row in queens))

    def test_out_of_their_range_the_plan_fights_the_gachapin(self):
        snapshot, navigator = self.board((26, 38), seen=(26, 44))
        read, queens = self.rows(snapshot, navigator, QUEEN)
        self.assertFalse(any(read.acts(row, (26, 38)) for row in queens))
        self.assertIsNone(quest_lure_approach.key(
            self.policy, snapshot, navigator, self.plan,
            quest_room_sweep._Board(self.policy, snapshot, self.policy.approved_quest_strategy(QUEST),
                                    navigator, self.plan)))
        self.decide(snapshot)
        self.assertNotIn(self.policy.last_reason, {quest_lure_approach.LURE_BACK_REASON,
                                                   quest_lure_approach.LURE_WALK_REASON})

    def test_a_queen_and_a_gachapin_together_the_player_disengages(self):
        snapshot, _navigator_ = self.board(LURE_START, seen=(24, 57), queen=(25, 62))
        self.decide(snapshot)
        self.assertTrue(self.policy.last_reason.startswith((quest_summon_answer.DISENGAGE_TELEPORT_REASON,
                                                            quest_summon_answer.DISENGAGE_WALK_REASON)))

    def test_the_gachapins_dead_the_queens_are_closed_on_from_the_forest(self):
        self.kills[GACHAPIN] = 3
        snapshot, navigator = self.board(QUEEN_STAND, gachapins=False)
        self.decide(snapshot)
        self.assertEqual(self.policy.last_reason, quest_lure_approach.APPROACH_WALK_REASON)
        path = self.paths[-1][1]
        self.assertEqual(path[-1], FOREST_STAND)
        terrain = navigator.battlefield.terrain
        self.assertIn("tree", {terrain[cell] for cell in path})
        read, queens = self.rows(snapshot, navigator, QUEEN)
        self.assertFalse(any(quest_lure_approach._line_of_fire(read, row, cell) for row in queens for cell in path))
        # From there the granite of the Queens' room melted lets one Queen alone see the player.
        self.assertIn(QUEEN_WALL, navigator.battlefield.stone_walls)
        self.assertEqual(quest_lure_approach._lines_at(read, queens, FOREST_STAND, read.open_cells | {QUEEN_WALL}), 1)
        there, _navigator_ = self.board(FOREST_STAND, gachapins=False)
        self.decide(there)
        self.assertTrue(self.policy.last_reason.startswith(quest_lure_approach.MELT_REASON))

    def test_the_border_is_permanent(self):
        _snapshot, navigator = self.board(QUEEN_STAND)
        self.assertNotIn((0, 40), navigator.battlefield.stone_walls)
        self.assertNotIn((23, 79), navigator.battlefield.stone_walls)


if __name__ == "__main__":
    unittest.main()
