"""n1-c life-217, Quest 33 段2 (2026-11-19 20:31-20:59): the Queen Ants never came to [14,47].

After the hand-added stand [18,39] the Dagons and the Bokrugs died (20:24-20:30) and 段2 opened: the
plan held [14,47] 300 turns for the three Queen Ants, which never came, then walked every 段1 stand
again, holding each one's meet_turns ([13,39] [11,39] [2,46] [2,30] [5,10] [14,10] [15,38] [18,39]
[14,47] ...), nine rounds until the floor-dwell watcher halted it at 20:59
(tests/fixtures/n1c-217-q33-queen-wait-1119.json.gz, tests/extract_n1c_217_q33_queen_wait_1119_fixture.py).

The reader (quest_wait_placement), owner 2026-11-19 「地形と敵の位置、敵のアルゴリズムを確認して有効な場所で待つ」:

* At [14,47] the Queens act (27 from [22,70], vision 30) and the flyers' flow reaches them within its
  32 steps (grid.cpp update_flow), but followed step by step as the game moves them (the point 16
  grids past the player, quest_wait_placement ``walks``) they do not come: the recorded nine rounds.
  The Gachapins (vision 10) do not act there, the Queens' way north over the pits passes none of their
  lines.  A cell where the Queens' way passes the Gachapins' mouth (the lower floor, [25,44]) is not
  chosen (``_passes_the_other_side``).  The corridor east of x=50 is where both sides act.
* The 段1 stands bring nothing of 段1 any more: [5,10] and [14,10] are passed, and the waits around the
  others are held only for what the board shows coming (the wandering ボーシン), each once.
* A wait run out with nothing come is spent: the Queens are then waited for only nearer than before.
  The recorded board has one such cell left in reach ([15,48]); after it the plan has no next step
  (段3 waits for the Queens' death) and the sweep stops by name, ``quest:blocked:sweep-nothing-comes``,
  instead of walking the round again.

The plan now lures the Gachapins and closes on the Queens in 段2 (owner 2026-11-19, quest_lure_approach);
these tests read the wait reader alone, the plan without ``lure_approach``.

DECLARED CONSTRUCTED: the policy is n1-c life-217's town arrival of the same day
(tests/fixtures/quest32-one-turn-kill-1119/n1c-217, tests/test_quest33_alignment_split ``recorded``);
the board is the recorded last one on [14,47] (the player moved on it for the later boards); the kill
lines of the three Its, Dagons and Bokrugs are set on the navigator (the run killed them, 18:30 and
20:24-20:30); each hold is run out by setting the stop's held turns to its meet_turns.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot import quest_alignment_split, quest_room_sweep, quest_wait_placement
from hengbot.model import parse_snapshot
from hengbot.policy_constants import WAIT_KEY
from hengbot.quest_plan_base import _navigator
from tests.test_quest33_alignment_split import BOKRUG, DAGON, IT, QUEEN, QUEST, quest_dir, recorded

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-217-q33-queen-wait-1119.json.gz"
QUEEN_STAND = (14, 47)


class N1c217Q33QueenWaitTest(unittest.TestCase):
    def setUp(self):
        if quest_dir() is None:
            self.skipTest("the Hengband quest data is not available")
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            self.case = json.load(stream)
        self.scratch, self.policy, _town = recorded("n1c-217")
        self.addCleanup(self.scratch.cleanup)
        self.board = self.at(QUEEN_STAND)
        # The reader alone: the 段2 lure and approach the owner decided afterwards
        # (quest_lure_approach, tests/test_n1c_217_q33_queen_approach_1119_recorded) taken off the plan.
        self.plan = {key: value for key, value in
                     self.policy.approved_quest_strategy(QUEST).engagement_plan["room_sweep"].items()
                     if key != "lure_approach"}
        self.navigator = _navigator(self.policy, self.board, QUEST)
        self.navigator.split_kills = {IT: 3, DAGON: 3, BOKRUG: 3}
        self.stops = quest_room_sweep._stops(self.plan)
        self.navigator.sweep_stage = self.stage(QUEEN_STAND)

    def at(self, cell):
        raw = copy.deepcopy(self.case["board"])
        raw["player"]["y"], raw["player"]["x"] = cell
        return parse_snapshot(raw, self.policy._monrace_knowledge)

    def stage(self, cell):
        return next(index for index, stop in enumerate(self.stops) if tuple(stop.get("cell")) == cell)

    def queens(self, keys):
        return {key for key in keys if key[0] == "placed" and key[1] == QUEEN}

    def test_the_recorded_rounds_held_every_stand_again(self):
        held = [tuple(run["cell"]) for run in self.case["runs"]
                if run["reason"] == "quest-strategy:hold" and run["time"] >= "2026-11-19T20:31"]
        self.assertGreaterEqual(held.count(QUEEN_STAND), 8)
        self.assertGreaterEqual(held.count((5, 10)), 8)
        self.assertGreaterEqual(held.count((14, 10)), 8)

    def test_the_queens_act_at_their_stand_but_do_not_come(self):
        # As the game moves them (quest_wait_placement ``walks``): the recorded nine rounds of 300.
        self.assertFalse(any(m.race_id == QUEEN for m in (*self.board.visible_monsters, *self.board.detected_monsters)))
        read = quest_wait_placement.reader(self.policy, self.board, self.navigator, self.plan)
        queens = [row for row in read.rows if row.race == QUEEN]
        self.assertEqual(len(queens), 3)
        self.assertTrue(all(read.acts(row, QUEEN_STAND) for row in queens))
        comers = quest_wait_placement.comers_at(self.policy, self.board, self.navigator, self.plan, QUEEN_STAND)
        self.assertEqual(self.queens(comers), set())

    def test_no_cell_where_the_queens_pass_the_gachapins(self):
        read = quest_wait_placement.reader(self.policy, self.board, self.navigator, self.plan)
        mouth = (25, 44)
        keys = frozenset(row.key for row in read.rows if row.race == QUEEN)
        self.assertEqual(len(keys), 3)
        self.assertFalse(read.both_sides_act(mouth))
        choice = quest_wait_placement.Choice(mouth, keys, 0.0)
        self.assertTrue(quest_wait_placement._passes_the_other_side(self.policy, self.navigator, self.plan, read, choice))
        stand = quest_wait_placement.Choice(QUEEN_STAND, keys, 0.0)
        self.assertFalse(quest_wait_placement._passes_the_other_side(self.policy, self.navigator, self.plan, read, stand))
        self.assertIn((15, 60), quest_alignment_split.refused_cells(self.policy, self.board, self.navigator, self.plan))

    def test_the_first_phase_stands_bring_nothing_of_their_phase(self):
        for stand in [(5, 10), (14, 10)]:
            self.assertIsNone(quest_wait_placement.choose(self.policy, self.board, self.navigator, self.plan, stand))

    def test_the_round_ends_by_name_instead_of_looping(self):
        board, holds = self.board, []
        for _ in range(120):
            key = quest_room_sweep._advance(self.policy, board, self.navigator, self.plan)
            reason = self.policy.last_reason
            if reason == quest_room_sweep.NOTHING_COMES_REASON:
                break
            stop = self.stops[self.navigator.sweep_stage]
            if reason == quest_room_sweep.HOLD_REASON:
                holds.append((tuple(stop["cell"]), (board.player.position.y, board.player.position.x)))
                self.navigator.sweep_meet_turns = int(stop["meet_turns"])
            else:
                self.assertEqual(reason, quest_room_sweep.WALK_REASON, key)
                held = self.navigator.wait_goal
                board = self.at(held[2].cell if held and held[2] is not None else tuple(stop["cell"]))
        self.assertEqual(self.policy.last_reason, quest_room_sweep.NOTHING_COMES_REASON)
        self.assertNotIn(QUEEN_STAND, [cell for _stand, cell in holds])  # the Queens do not come there
        waited = [cell for _stand, cell in holds]
        self.assertEqual(len(waited), len(set(waited)))  # no waiting cell twice
        self.assertLessEqual(len(holds), 6)
        stands = {stand for stand, _cell in holds}
        self.assertFalse({(5, 10), (14, 10)} & stands)
        # Stopped, it stays stopped while nothing changes.
        self.assertEqual(quest_room_sweep._advance(self.policy, board, self.navigator, self.plan), WAIT_KEY)
        self.assertEqual(self.policy.last_reason, quest_room_sweep.NOTHING_COMES_REASON)


if __name__ == "__main__":
    unittest.main()
