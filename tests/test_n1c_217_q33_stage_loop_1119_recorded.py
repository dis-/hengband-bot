"""n1-c life-217, Quest 33 resumed (2026-11-19 19:25-20:00): the stands of 段1 walked round and round.

The run (tests/fixtures/n1c-217-q33-stage-loop-1119.json.gz, extracted by
tests/extract_n1c_217_q33_stage_loop_1119_fixture.py) walked [13,39] [11,39] [2,46] [2,30] [5,10]
[14,10] [15,38] and again, holding each stand's meet_turns, until the server's floor-dwell watcher
halted it.  The 段2 stand [14,47] was never reached: the Queens (vision 30) and the Dagons (vision 12)
both act there (quest_alignment_split ``contact_cells``), and it opens only once the Dagons are dead.
The plan waited for the Dagons at [15,38], but from there only the nearest of the three, [23,44] on
the recorded board, is within its vision of 12 (the game moves a monster only while the player is
within its vision or in his line within 20, monster-processor.cpp decide_process_continue).

Owner 2026-11-19 「地形と敵の位置、敵のアルゴリズムを確認して有効な場所で待つ」: the stand's wait is held where
the reader (quest_wait_placement) finds the awaited monsters come.  On the recorded board that is the
mouth of the central column [15,40], two steps from the stand, where all three Dagons act and walk to
the player; the hand-added stand [18,39] (commit 04330b279b) is gone from the plan, and after a wait
there runs out with nothing come, the next wait for the same Dagons is only nearer: [18,39] itself.

DECLARED CONSTRUCTED: the policy is n1-c life-217's town arrival of the same day
(tests/fixtures/quest32-one-turn-kill-1119/n1c-217, with the shipped strategies and this tree's quest
data, tests/test_quest33_alignment_split ``recorded``); the board is the recorded one on [15,38]
(the player moved on it for the later boards); the navigator is set on the [15,38] stand and the three
Its' kill lines read (the run killed 『それ』 three times at 18:30, quest_alignment_split counts them).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot import quest_exposure, quest_room_sweep, quest_wait_placement
from hengbot.model import Position, parse_snapshot
from hengbot.policy_constants import WAIT_KEY
from hengbot.quest_plan_base import _navigator
from tests.test_quest33_alignment_split import DAGON, IT, QUEST, quest_dir, recorded

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-217-q33-stage-loop-1119.json.gz"
STAND = [15, 38]
COLUMN_MOUTH = (15, 40)
COLUMN_TOP = (18, 39)


class N1c217Q33StageLoopTest(unittest.TestCase):
    def setUp(self):
        if quest_dir() is None:
            self.skipTest("the Hengband quest data is not available")
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            self.case = json.load(stream)
        self.scratch, self.policy, _town = recorded("n1c-217")
        self.addCleanup(self.scratch.cleanup)
        self.board = self.at((15, 38))
        self.plan = self.policy.approved_quest_strategy(QUEST).engagement_plan["room_sweep"]
        self.navigator = _navigator(self.policy, self.board, QUEST)
        self.navigator.split_kills = {IT: 3}
        stops = quest_room_sweep._stops(self.plan)
        self.navigator.sweep_stage = next(index for index, stop in enumerate(stops) if stop.get("cell") == STAND)

    def at(self, cell):
        raw = copy.deepcopy(self.case["board"])
        raw["player"]["y"], raw["player"]["x"] = cell
        return parse_snapshot(raw, self.policy._monrace_knowledge)

    def dagons(self):
        return sorted((m.position.y, m.position.x) for m in self.board.detected_monsters if m.race_id == DAGON)

    def dagon_keys(self):
        return {("seen", m.index) for m in self.board.detected_monsters if m.race_id == DAGON}

    def test_the_recorded_round_never_reached_the_queen_stand(self):
        held = {tuple(run["cell"]) for run in self.case["runs"] if run["reason"] == "quest-strategy:hold"}
        self.assertTrue({(13, 39), (11, 39), (2, 46), (2, 30), (5, 10), (14, 10), (15, 38)} <= held)
        self.assertNotIn((14, 47), held)
        self.assertFalse(any(run["cell"][0] >= 16 for run in self.case["runs"]))

    def test_the_hand_added_stand_is_gone(self):
        self.assertNotIn(list(COLUMN_TOP), [stop["cell"] for stop in self.plan["stands"]])

    def test_from_the_stand_one_dagon_acts_and_none_comes(self):
        self.assertEqual(self.dagons(), [(23, 44), (25, 44), (25, 45)])
        vision = self.policy._monrace_knowledge[DAGON].vision
        near = [cell for cell in self.dagons() if quest_exposure.game_distance(cell, (15, 38)) <= vision]
        self.assertEqual(near, [(23, 44)])
        comers = quest_wait_placement.comers_at(self.policy, self.board, self.navigator, self.plan, (15, 38))
        # The one acting goes back and forth at the wall of its room as the game moves it
        # (quest_wait_placement ``walks``, tests/test_n1c_217_q33_gachapin_wait_1119_recorded).
        self.assertEqual(comers & self.dagon_keys(), frozenset())

    def test_the_wait_is_held_where_all_three_dagons_come(self):
        key = quest_room_sweep.walk_key(self.policy, self.board)
        self.assertIsNotNone(key)
        self.assertEqual(self.policy.last_reason, quest_room_sweep.WALK_REASON)
        choice = self.navigator.wait_goal[2]
        self.assertEqual(choice.cell, COLUMN_MOUTH)
        self.assertTrue(self.dagon_keys() <= choice.keys)
        # Standing there: the plan's hold.
        there = self.at(COLUMN_MOUTH)
        self.assertEqual(quest_room_sweep.walk_key(self.policy, there), WAIT_KEY)
        self.assertEqual(self.policy.last_reason, quest_room_sweep.HOLD_REASON)

    def test_a_wait_run_out_is_not_walked_again_and_the_next_is_nearer(self):
        quest_room_sweep.walk_key(self.policy, self.board)
        there = self.at(COLUMN_MOUTH)
        quest_room_sweep.walk_key(self.policy, there)
        self.navigator.sweep_meet_turns = int(self.plan["stands"][self.navigator.sweep_stage]["meet_turns"])
        quest_room_sweep.walk_key(self.policy, there)
        # Spent: the Dagons are waited for from now on only nearer than from [15,40].
        spent = dict(self.navigator.wait_spent)
        self.assertTrue(self.dagon_keys() <= spent.keys())
        self.assertNotEqual(quest_room_sweep._stops(self.plan)[self.navigator.sweep_stage]["cell"], STAND)
        again = quest_wait_placement.choose(self.policy, there, self.navigator, self.plan, tuple(STAND))
        self.assertEqual(again.cell, COLUMN_TOP)
        self.assertTrue(self.dagon_keys() <= again.keys)


if __name__ == "__main__":
    unittest.main()
